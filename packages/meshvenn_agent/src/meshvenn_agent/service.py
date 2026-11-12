"""Provider-neutral action gateway; technical completion never certifies an asset."""
from __future__ import annotations

import json
import re
import uuid
from typing import Callable

from .artifacts import ArtifactStore
from .contracts import (ACTIONS, ACTION_VERSION, GATEWAY_VERSION, VERIFICATION_STATUSES,
                        GatewayError, GatewayLimits, check_cancel, decode_json, json_bytes,
                        validate_arguments, validate_request)
from .ports import EnginePort


def _error_status(code):
    if code == "cancelled":
        return "cancelled"
    if code in ("unavailable", "native_unavailable", "host_unavailable", "artifact_not_found", "artifact_unavailable"):
        return "unavailable"
    if code in ("invalid_request", "unknown_action", "invalid_input", "invalid_arguments", "validation_error",
                "unsupported_action", "stale_source", "stale_input", "hash_mismatch", "unsafe_artifact_path") or "stale" in code:
        return "invalid_request"
    return "failed"


def _safe_error(exc):
    if isinstance(exc, GatewayError):
        return exc
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    details = getattr(exc, "details", None)
    if type(code) is str and type(message) is str:
        return GatewayError(code[:128], message[:1024], details if type(details) is dict else {})
    return GatewayError("failed", f"The engine operation failed ({type(exc).__name__}).")


class Gateway:
    def __init__(self, engine: EnginePort, artifacts: ArtifactStore, *, limits: GatewayLimits | None = None):
        self.engine, self.artifacts = engine, artifacts
        self.limits = limits or GatewayLimits()

    def _capabilities(self):
        try:
            capabilities = self.engine.capabilities()
            raw = json_bytes(capabilities, max_bytes=self.limits.max_catalogue_bytes, limits=self.limits)
            capabilities = json.loads(raw)
        except Exception as exc:
            raise GatewayError("unavailable", "The configured engine could not provide a bounded capability catalogue.") from exc
        if (type(capabilities) is not dict or capabilities.get("schema_version") != 1 or
                type(capabilities.get("schema_version")) is not int or type(capabilities.get("actions")) is not dict or
                type(capabilities.get("engine_version")) is not str):
            raise GatewayError("unavailable", "The configured engine capability contract is unsupported.")
        return capabilities

    def catalogue(self):
        capabilities = self._capabilities()
        actions = []
        for name in ACTIONS:
            declared = capabilities["actions"].get(name, {})
            supported = type(declared) is dict and type(declared.get("version")) is int and declared.get("version") == ACTION_VERSION
            available = supported and declared.get("available") is True
            reason = declared.get("reason", "") if supported else "The engine does not advertise this action version."
            schemas = {field: declared.get(field, {"type": "object", "additionalProperties": False})
                       if supported else {"type": "object", "additionalProperties": False}
                       for field in ("input_schema", "output_schema")}
            if any(type(schema) is not dict for schema in schemas.values()):
                available, reason = False, "The engine action schema is unavailable."
                schemas = {field: {"type": "object", "additionalProperties": False} for field in schemas}
            actions.append(dict(name=name, version=ACTION_VERSION, available=available,
                reason=str(reason)[:1024], **schemas,
                annotations=dict(readOnlyHint=name == "engine.capabilities", destructiveHint=False,
                                 idempotentHint=name == "engine.capabilities", openWorldHint=False,
                                 supportsCancellation=name != "engine.capabilities",
                                 requiresNative=name in ("geometry.diagnose", "geometry.mesh"),
                                 technicalCompletionIsVerification=False)))
        result = dict(schema_version=1, gateway_version=GATEWAY_VERSION,
                      engine_version=capabilities["engine_version"], actions=actions)
        json_bytes(result, max_bytes=self.limits.max_catalogue_bytes, limits=self.limits)
        return result

    def _envelope(self, request_id, action, *, status, verification="unknown", result=None, report=None,
                  summary=None, artifact=None, error=None):
        technical = "completed" if status == "completed" else "not_started" if status in ("invalid_request", "unavailable") else status
        return dict(schema_version=1, request_id=request_id, action=action, action_version=ACTION_VERSION,
                    status=status, technical_status=technical, verification_status=verification,
                    result=result, report=report, summary=summary or {}, artifact=artifact, error=error)

    def _failure(self, request_id, action, exc, *, engine_invoked=False):
        error = _safe_error(exc)
        details = error.details
        try:
            json_bytes(details, max_bytes=2048, limits=self.limits)
        except GatewayError:
            details = {"truncated": True}
        response = self._envelope(request_id, action, status=_error_status(error.code),
                                  error=dict(code=error.code[:128], message=error.message[:1024], details=details))
        if engine_invoked and response["technical_status"] == "not_started":
            response["technical_status"] = "failed"
        try:
            json_bytes(response, max_bytes=self.limits.max_response_bytes, limits=self.limits)
        except GatewayError:
            response["error"]["details"] = {"truncated": True}
            response["error"]["code"] = error.code[:128] if re.fullmatch(r"[A-Za-z0-9_.:-]+", error.code) else "failed"
            response["error"]["message"] = error.message.encode("utf-8", "replace")[:128].decode("utf-8", "ignore")
        return response

    def execute(self, action: str, arguments: dict, *, request_id: str | None = None,
                cancel: Callable[[], bool] | None = None):
        request = dict(schema_version=1, request_id=request_id if request_id is not None else uuid.uuid4().hex,
                       action=action, action_version=ACTION_VERSION, arguments=arguments)
        return self.invoke(request, cancel=cancel)

    def invoke_json(self, request: str | bytes, *, cancel: Callable[[], bool] | None = None):
        try:
            return self.invoke(decode_json(request, limits=self.limits), cancel=cancel)
        except Exception as exc:
            return self._failure("invalid", "unknown", exc)

    def invoke(self, request: dict, *, cancel: Callable[[], bool] | None = None):
        request_id, action = "invalid", "unknown"
        engine_invoked = False
        try:
            # Round-trip the validated request before invoking a mutable external
            # port. Host code cannot race later changes into this source snapshot.
            raw = json_bytes(request, max_bytes=self.limits.max_request_bytes, limits=self.limits, cancel=cancel)
            request = json.loads(raw)
            if type(request) is dict:
                if type(request.get("request_id")) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request["request_id"]):
                    request_id = request["request_id"]
                if type(request.get("action")) is str and request["action"] in ACTIONS:
                    action = request["action"]
            validate_request(request)
            request_id, action = request["request_id"], request["action"]
            arguments = request["arguments"]
            validate_arguments(action, arguments)
            check_cancel(cancel)
            capabilities = self._capabilities()
            declared = capabilities["actions"].get(action, {})
            if (type(declared) is not dict or type(declared.get("version")) is not int or
                    declared.get("version") != ACTION_VERSION or declared.get("available") is not True):
                raise GatewayError("unavailable", "The configured engine does not currently provide this action.",
                                   {"action": action, "reason": str(declared.get("reason", "Not advertised"))[:512] if type(declared) is dict else "Invalid capability"})
            engine_invoked = True
            value = self.engine.execute(action, arguments, cancel=cancel)
            try:
                encoded = json_bytes(value, max_bytes=self.limits.max_response_bytes, limits=self.limits)
                if type(value) is not dict:
                    raise GatewayError("invalid_engine_output", "Engine actions must return a JSON object.")
                value = json.loads(encoded)
            except GatewayError as exc:
                raise GatewayError("invalid_engine_output", "The engine response exceeds or violates the finite JSON contract.", exc.details) from exc
            # The engine alone derives D1 verification. No mean, successful call,
            # mesh creation, or absence of failed findings invents a PASS here.
            verification = value.get("verification_status", "not_applicable" if action == "engine.capabilities" else "unknown")
            if type(verification) is not str or verification not in VERIFICATION_STATUSES:
                raise GatewayError("invalid_engine_output", "The engine returned an unsupported verification status.")
            report = value.get("report") if type(value.get("report")) is dict else None
            if verification == "pass" and (action == "geometry.mesh" or report is None or report.get("completion") != "complete"):
                raise GatewayError("invalid_engine_output", "A geometric PASS requires the engine's completed diagnostic report; mesh construction is technical only.")
            cancelled = (cancel is not None and cancel()) or (report is not None and report.get("completion") == "cancelled")
            if len(encoded) > self.limits.max_artifact_bytes:
                raise GatewayError("artifact_too_large", "The returned artifact exceeds the gateway storage budget.")
            artifact = self.artifacts.put_bytes(encoded, media_type="application/json").to_dict()
            inline = json.loads(encoded) if len(encoded) <= self.limits.max_inline_bytes else None
            summary = self._summary(value)
            embedded_report = None
            if report is not None and len(json_bytes(report, max_bytes=self.limits.max_response_bytes, limits=self.limits)) <= self.limits.max_report_bytes:
                embedded_report = report
            envelope = self._envelope(request_id, action, status="cancelled" if cancelled else "completed",
                verification="unknown" if cancelled else verification, result=inline, report=embedded_report,
                summary=summary, artifact=artifact,
                error={"code": "cancelled", "message": "The operation was cancelled; its returned artifact was retained.", "details": {}} if cancelled else None)
            json_bytes(envelope, max_bytes=self.limits.max_response_bytes, limits=self.limits)
            return envelope
        except Exception as exc:
            return self._failure(request_id, action, exc, engine_invoked=engine_invoked)

    def _summary(self, value):
        summary = dict(result_keys=[str(key)[:80] for key in sorted(value)[:24]])
        report = value.get("report")
        if type(report) is dict:
            findings = report.get("findings", [])
            if type(findings) is not list:
                findings = []
            counts = {status: 0 for status in sorted(VERIFICATION_STATUSES)}
            for finding in findings:
                if type(finding) is dict and finding.get("status") in counts:
                    counts[finding["status"]] += 1
            summary["report"] = dict(report_id=str(report.get("report_id", ""))[:128],
                                     completion=str(report.get("completion", "unknown"))[:32],
                                     finding_count=len(findings), finding_counts=counts,
                                     verification_authority="engine")
        for label in ("volume", "mesh"):
            source = value.get(label)
            if type(source) is dict:
                summary[label] = {name: source[name] for name in
                    ("width", "depth", "height", "occupied_count", "vertex_count", "triangle_count", "polygon_count", "sha256")
                    if name in source and type(source[name]) in (int, float, str)}
                summary[label] = {name: item[:128] if type(item) is str else item for name, item in summary[label].items()}
        for name in ("requested_resolution", "actual_resolution"):
            if type(value.get(name)) is int:
                summary[name] = value[name]
        if type(value.get("attempts")) is list:
            summary["attempt_count"] = len(value["attempts"])
        return summary

    def read_artifact(self, sha256: str, *, offset: int = 0, limit: int = 64*1024):
        try:
            if type(offset) is not int or not 0 <= offset <= self.artifacts.max_artifact_bytes:
                raise GatewayError("invalid_request", "Artifact offset exceeds the bounded store profile.")
            if type(limit) is not int or limit > self.limits.max_chunk_bytes:
                raise GatewayError("invalid_request", "Artifact read exceeds the gateway chunk budget.")
            return self.artifacts.read(sha256, offset=offset, limit=limit)
        except Exception as exc:
            error = _safe_error(exc)
            return dict(schema_version=1, status=_error_status(error.code), sha256=sha256[:64] if type(sha256) is str else "",
                        offset=offset if type(offset) is int and 0 <= offset <= self.artifacts.max_artifact_bytes else 0, bytes=0, total_bytes=None, eof=False,
                        next_offset=None, data_base64="", error=error.to_dict())
