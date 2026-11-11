"""Bounded, versioned JSON contracts; independent of engines and SDKs."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Callable

SCHEMA_VERSION = 1
ACTION_VERSION = 1
GATEWAY_VERSION = "0.1.0"
ACTIONS = ("engine.capabilities", "views.preflight", "geometry.diagnose", "geometry.mesh")
VERIFICATION_STATUSES = frozenset(("pass", "fail", "unknown", "not_applicable"))


class GatewayError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}

    def to_dict(self):
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class GatewayLimits:
    max_request_bytes: int = 64 * 1024 * 1024
    max_response_bytes: int = 256 * 1024 * 1024
    max_inline_bytes: int = 16 * 1024
    max_report_bytes: int = 12 * 1024
    max_catalogue_bytes: int = 512 * 1024
    max_artifact_bytes: int = 256 * 1024 * 1024
    max_chunk_bytes: int = 64 * 1024
    max_depth: int = 32
    max_nodes: int = 20_000_000

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        for name in ("max_request_bytes", "max_response_bytes", "max_artifact_bytes"):
            if getattr(self, name) > 512 * 1024 * 1024:
                raise ValueError(f"{name} exceeds the 512 MiB host profile cap.")
        if (self.max_depth > 64 or self.max_nodes > 20_000_000 or self.max_chunk_bytes > 1024 * 1024 or
                self.max_inline_bytes > 1024 * 1024 or self.max_catalogue_bytes > 2 * 1024 * 1024 or
                self.max_inline_bytes > self.max_response_bytes or self.max_report_bytes > 1024 * 1024 or
                self.max_report_bytes > self.max_response_bytes):
            raise ValueError("Gateway limits exceed the bounded host profile.")


def check_cancel(cancel: Callable[[], bool] | None):
    if cancel is not None and cancel():
        raise GatewayError("cancelled", "The operation was cancelled.")


def json_bytes(value: Any, *, max_bytes: int, limits: GatewayLimits,
               cancel: Callable[[], bool] | None = None) -> bytes:
    """Reject Python objects/coercions before taking an immutable JSON snapshot."""
    count = 0

    def walk(item, depth):
        nonlocal count
        count += 1
        if count % 1024 == 1:
            check_cancel(cancel)
        if count > limits.max_nodes or depth > limits.max_depth:
            raise GatewayError("invalid_request", "JSON exceeds its node/depth budget.")
        kind = type(item)
        if item is None or kind in (str, bool, int):
            return
        if kind is float:
            if not math.isfinite(item):
                raise GatewayError("invalid_request", "JSON numbers must be finite.")
            return
        if kind is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise GatewayError("invalid_request", "JSON object keys must be strings.")
                walk(child, depth + 1)
            return
        if kind is list:
            for child in item:
                walk(child, depth + 1)
            return
        raise GatewayError("invalid_request", "Only JSON scalar, array and object values are accepted.")

    walk(value, 0)
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise GatewayError("invalid_request", "The value is not finite UTF-8 JSON.") from exc
    if len(encoded) > max_bytes:
        raise GatewayError("invalid_request", "JSON exceeds the configured byte budget.",
                           {"bytes": len(encoded), "limit": max_bytes})
    check_cancel(cancel)
    return encoded


def decode_json(payload: str | bytes, *, limits: GatewayLimits | None = None):
    limits = limits or GatewayLimits()
    try:
        raw = payload.encode("utf-8") if type(payload) is str else payload
        if type(raw) is not bytes or len(raw) > limits.max_request_bytes:
            raise GatewayError("invalid_request", "Request exceeds its byte budget or is not UTF-8 JSON.")

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise GatewayError("invalid_request", "Duplicate JSON fields are not accepted.")
                result[key] = value
            return result

        def nonfinite(_):
            raise GatewayError("invalid_request", "Nonfinite JSON numbers are not accepted.")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise GatewayError("invalid_request", "Malformed UTF-8 JSON request.") from exc
    json_bytes(value, max_bytes=limits.max_request_bytes, limits=limits)
    return value


def validate_request(request: dict):
    fields = {"schema_version", "request_id", "action", "action_version", "arguments"}
    if type(request) is not dict or set(request) != fields:
        raise GatewayError("invalid_request", "Request must contain exactly the version, ID, action and arguments fields.")
    if type(request["schema_version"]) is not int or request["schema_version"] != SCHEMA_VERSION:
        raise GatewayError("invalid_request", "Unsupported request schema version.")
    if type(request["action_version"]) is not int or request["action_version"] != ACTION_VERSION:
        raise GatewayError("invalid_request", "Unsupported action version.")
    if type(request["request_id"]) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request["request_id"]):
        raise GatewayError("invalid_request", "request_id must be a stable identifier of at most 128 characters.")
    if type(request["action"]) is not str or request["action"] not in ACTIONS:
        raise GatewayError("unknown_action", "The requested action is not supported.")
    if type(request["arguments"]) is not dict:
        raise GatewayError("invalid_request", "Action arguments must be a JSON object.")


ALLOWED_ARGUMENTS = {
    "engine.capabilities": frozenset(),
    "views.preflight": frozenset(("view_set", "inputs", "policy", "anchors")),
    "geometry.diagnose": frozenset(("view_set", "inputs", "policy", "regions")),
    "geometry.mesh": frozenset(("volume", "voxel_size", "center_xy", "mesh_mode", "max_seconds")),
}
REQUIRED_ARGUMENTS = {
    "engine.capabilities": frozenset(),
    "views.preflight": frozenset(("view_set", "inputs")),
    "geometry.diagnose": frozenset(("view_set", "inputs")),
    "geometry.mesh": frozenset(("volume",)),
}


def validate_arguments(action: str, arguments: dict):
    if set(arguments) - ALLOWED_ARGUMENTS[action]:
        raise GatewayError("invalid_request", "Unknown action arguments are not accepted; host paths and backend/trust configuration are not agent inputs.")
    missing = REQUIRED_ARGUMENTS[action] - set(arguments)
    if missing:
        raise GatewayError("invalid_request", "Required action arguments are missing.", {"missing": sorted(missing)})
    for name in ("view_set", "inputs", "policy", "volume"):
        if name in arguments and type(arguments[name]) is not dict:
            raise GatewayError("invalid_request", f"{name} must be a JSON object.")
    for name in ("anchors", "regions"):
        if name in arguments and type(arguments[name]) is not list:
            raise GatewayError("invalid_request", f"{name} must be a JSON array.")
    forbidden = {"native_library", "native_library_path", "library_path", "python_executable", "backend",
                 "workspace", "allow_unverified", "trust_inputs", "trusted", "allow_paths", "source_path", "file_path", "path"}

    def inspect(value):
        if type(value) is dict:
            if forbidden.intersection(value):
                raise GatewayError("invalid_request", "Backend, local path and trust overrides are host configuration, not action arguments.")
            for child in value.values():
                if type(child) in (dict, list):
                    inspect(child)
        elif type(value) is list:
            for child in value:
                if type(child) in (dict, list):
                    inspect(child)
    inspect(arguments)
