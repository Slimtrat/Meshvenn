"""Analytic two-link solve with explicit reach residual, without stretching."""
from __future__ import annotations

from dataclasses import dataclass
import math


def _point(value):
    if len(value) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("IK points require three finite coordinates")
    return tuple(value)


def _sub(a, b): return tuple(x - y for x, y in zip(a, b))
def _add(a, b): return tuple(x + y for x, y in zip(a, b))
def _scale(a, t): return tuple(x * t for x in a)
def _dot(a, b): return sum(x * y for x, y in zip(a, b))


@dataclass(frozen=True)
class TwoBoneSolution:
    knee: tuple[float, float, float]
    ankle: tuple[float, float, float]
    reach_error: float


def solve_two_bone(hip, knee, ankle, goal, *, pole=(0., -1., 0.)):
    hip, knee, ankle, goal, pole = map(_point, (hip, knee, ankle, goal, pole))
    first, second = math.dist(hip, knee), math.dist(knee, ankle)
    scale = first + second
    if not math.isfinite(scale) or min(first, second) <= 1e-10:
        raise ValueError("IK requires two nonzero finite links")
    if min(first, second) / scale < 1e-6:
        raise ValueError("IK link ratio is too ill-conditioned for a length-preserving solve")
    direction = _sub(goal, hip)
    distance = math.hypot(*direction)
    if not math.isfinite(distance):
        raise ValueError("IK goal distance is not representable")
    if distance < scale * 1e-10:
        direction = _sub(ankle, hip)
        distance_hint = math.hypot(*direction)
        direction = _scale(direction, 1 / distance_hint) if distance_hint > scale * 1e-10 else (0., 0., -1.)
    else:
        direction = _scale(direction, 1 / distance)
    epsilon = scale * 1e-7
    reach = min(scale - epsilon, max(abs(first - second) + epsilon, distance))
    # Normalize before squaring to avoid overflow/underflow at large scales.
    a, b, d = first / scale, second / scale, reach / scale
    along_normalized = (a * a - b * b + d * d) / (2 * d)
    along = scale * along_normalized
    bend = scale * math.sqrt(max(0., a * a - along_normalized * along_normalized))
    # Preserve the FK bend plane unless the chain is nearly straight/folded.
    hint = _sub(knee, hip)
    perpendicular = _sub(hint, _scale(direction, _dot(hint, direction)))
    if math.hypot(*perpendicular) < scale * 1e-4:
        perpendicular = _sub(pole, _scale(direction, _dot(pole, direction)))
    if math.hypot(*perpendicular) < 1e-10:
        axis = min(((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)), key=lambda a: abs(_dot(a, direction)))
        perpendicular = _sub(axis, _scale(direction, _dot(axis, direction)))
    perpendicular = _scale(perpendicular, 1 / math.hypot(*perpendicular))
    solved_knee = _add(hip, _add(_scale(direction, along), _scale(perpendicular, bend)))
    solved_ankle = _add(hip, _scale(direction, reach))
    return TwoBoneSolution(_point(solved_knee), _point(solved_ankle), math.dist(solved_ankle, goal))
