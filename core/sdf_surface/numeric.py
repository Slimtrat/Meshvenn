from __future__ import annotations

import math

from .models import EPSILON, Vector3


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def normalize3(value: Vector3) -> Vector3:
    length = math.sqrt(
        value[0] * value[0] + value[1] * value[1] + value[2] * value[2]
    )
    if length <= EPSILON:
        return 0.0, 0.0, 0.0
    inverse = 1.0 / length
    return value[0] * inverse, value[1] * inverse, value[2] * inverse


def average_points(values: list[Vector3]) -> Vector3:
    if not values:
        raise ValueError("Cannot average an empty point collection.")
    inverse = 1.0 / float(len(values))
    return (
        sum(value[0] for value in values) * inverse,
        sum(value[1] for value in values) * inverse,
        sum(value[2] for value in values) * inverse,
    )


def edge_crosses_iso(first: float, second: float, iso_level: float) -> bool:
    first_inside = float(first) <= iso_level
    second_inside = float(second) <= iso_level
    return first_inside != second_inside


def edge_interpolation(first: float, second: float, iso_level: float) -> float:
    denominator = float(second) - float(first)
    if abs(denominator) <= EPSILON:
        return 0.5
    return clamp01((iso_level - float(first)) / denominator)


def interpolate3(first: Vector3, second: Vector3, factor: float) -> Vector3:
    return (
        first[0] + (second[0] - first[0]) * factor,
        first[1] + (second[1] - first[1]) * factor,
        first[2] + (second[2] - first[2]) * factor,
    )


def append_unique_point(values: list[Vector3], point: Vector3) -> None:
    for existing in values:
        if (
            abs(existing[0] - point[0]) <= EPSILON
            and abs(existing[1] - point[1]) <= EPSILON
            and abs(existing[2] - point[2]) <= EPSILON
        ):
            return
    values.append(point)
