"""Strict JSON primitives shared by the modular-character contract."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence


_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def fields(value, required, *, name, optional=()):
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object.")
    unknown = set(value) - set(required) - set(optional)
    missing = set(required) - set(value)
    if unknown or missing:
        raise ValueError(f"{name} has unknown fields {sorted(map(str, unknown))} "
                         f"or missing fields {sorted(missing)}.")
    return value


def text(value, *, name):
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(ord(char) < 32 for char in value)):
        raise ValueError(f"{name} must be a nonempty unpadded string without control characters.")
    return value


def identifier(value, *, name):
    value = text(value, name=name)
    if not _ID.fullmatch(value):
        raise ValueError(f"{name} must be a stable lowercase identifier.")
    return value


def sha256(value, *, name):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must contain 64 lowercase hexadecimal characters.")
    return value


def integer(value, *, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def number(value, *, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite.") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive." if positive else "."))
    return result


def sequence(value, *, name):
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be an array.")
    return tuple(value)


def vector(value, size, *, name, positive=False):
    values = sequence(value, name=name)
    if len(values) != size:
        raise ValueError(f"{name} must have {size} components.")
    return tuple(number(item, name=name, positive=positive) for item in values)


def unique(values, *, name):
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique; ambiguous declarations are not supported.")
