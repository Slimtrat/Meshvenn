"""Strict, deterministic JSON for the diagnostic boundary (no runtime services)."""

from __future__ import annotations

import hashlib
import json
import math
import re
import types
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import Union, get_args, get_origin, get_type_hints


def require_text(value: str, name: str) -> None:
    if not value or value != value.strip():
        raise ValueError(f"{name} must be nonempty text without surrounding whitespace.")


def require_id(value: str, name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value):
        raise ValueError(f"{name} must be a stable identifier.")


def require_sha256(value: str, name: str = "sha256") -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest.")


def require_version(value: int) -> None:
    if type(value) is not int or value != 1:
        raise ValueError("Unsupported diagnostic schema_version; expected 1.")


def unique(values, name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique.")


def positive(value: int, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def _convert(value, annotation, path: str, *, decode: bool):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                return _convert(value, option, path, decode=decode)
            except (ValueError, TypeError):
                pass
        raise ValueError(f"{path} has an invalid type or value.")
    if annotation is type(None):
        if value is not None:
            raise ValueError(f"{path} must be null.")
        return None
    if origin is tuple:
        if type(value) not in (list, tuple):
            raise ValueError(f"{path} must be an array.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_convert(v, args[0], f"{path}[{i}]", decode=decode)
                         for i, v in enumerate(value))
        if len(args) != len(value):
            raise ValueError(f"{path} has an invalid array length.")
        return tuple(_convert(v, t, f"{path}[{i}]", decode=decode)
                     for i, (v, t) in enumerate(zip(value, args)))
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        if not isinstance(value, (str, annotation)):
            raise ValueError(f"{path} must be an enum string.")
        return annotation(value)
    if is_dataclass(annotation):
        if decode:
            return _decode_model(annotation, value, path)
        if type(value) is not annotation:
            raise ValueError(f"{path} must be {annotation.__name__}.")
        validate_model(value)
        return value
    if annotation is float:
        if type(value) not in (int, float):
            raise ValueError(f"{path} must be a finite number.")
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError(f"{path} must be finite.") from exc
        if not math.isfinite(number):
            raise ValueError(f"{path} must be finite.")
        return 0.0 if number == 0 else number
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ValueError(f"{path} must be {annotation.__name__}.")
        return value
    raise TypeError(f"Unsupported contract field type: {annotation!r}")


@lru_cache(maxsize=256)
def _model_annotations(model):
    # Versioned contract classes have static schemas. Cache only reflection,
    # never instances, converted values or validation outcomes. Reloaded module
    # classes are distinct keys; untrusted JSON cannot supply a class object.
    return get_type_hints(model)


def validate_model(value) -> None:
    """Normalize enum/tuple/numeric fields and reject coercion of JSON scalars."""
    annotations = _model_annotations(type(value))
    for field in fields(value):
        converted = _convert(getattr(value, field.name), annotations[field.name],
                             field.name, decode=False)
        object.__setattr__(value, field.name, converted)


def _decode_model(model, data, path: str):
    if type(data) is not dict or any(type(key) is not str for key in data):
        raise ValueError(f"{path} must be a JSON object.")
    model_fields = {field.name: field for field in fields(model)}
    extra = set(data) - set(model_fields)
    if extra:
        raise ValueError(f"{path} contains unsupported fields: {sorted(extra)}")
    if "schema_version" in model_fields and "schema_version" not in data:
        raise ValueError(f"{path}.schema_version is required.")
    annotations = _model_annotations(model)
    kwargs = {}
    for name, field in model_fields.items():
        if name in data:
            kwargs[name] = _convert(data[name], annotations[name], f"{path}.{name}", decode=True)
        elif field.default is MISSING and field.default_factory is MISSING:
            raise ValueError(f"{path}.{name} is required.")
    try:
        return model(**kwargs)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def _encode(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def content_sha256(content: bytes) -> str:
    if type(content) is not bytes:
        raise ValueError("Content hashes require exact bytes.")
    return hashlib.sha256(content).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Nonfinite JSON number: {value}")


class JsonContract:
    def to_dict(self) -> dict:
        validate_model(self)
        return _encode(self)

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        return _decode_model(cls, data, cls.__name__)

    @classmethod
    def from_json(cls, content: str):
        if type(content) is not str:
            raise ValueError("JSON content must be text.")
        try:
            data = json.loads(content, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("Malformed diagnostic JSON.") from exc
        return cls.from_dict(data)
