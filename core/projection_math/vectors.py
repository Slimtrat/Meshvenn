from __future__ import annotations

import math

from .models import EPSILON


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def dot3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def normalize3(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in value))
    if length <= EPSILON:
        return (0.0, 0.0, 0.0)
    inverse = 1.0 / length
    return tuple(component * inverse for component in value)
