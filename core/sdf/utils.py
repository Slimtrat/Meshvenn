from __future__ import annotations

import math


def require_finite(value: float, *, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def lerp(a: float, b: float, t: float) -> float:
    return float(a) + (float(b) - float(a)) * float(t)
