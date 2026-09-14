from __future__ import annotations

from typing import Iterable, Sequence

from ..projection_math import NormalizedPoint
from .constants import DEFAULT_SMOOTHNESS, DEFAULT_SURFACE_OFFSET, DEFAULT_SYMMETRY_X
from .projection import SDFProjection
from .utils import require_finite


def smooth_max(a: float, b: float, smoothness: float) -> float:
    """Polynomial smooth maximum used for SDF intersection."""
    a, b = require_finite(a, name="a"), require_finite(b, name="b")
    smoothness = require_finite(smoothness, name="smoothness")
    if smoothness < 0.0:
        raise ValueError("smoothness cannot be negative.")
    if smoothness <= 0.0:
        return max(a, b)
    difference = abs(a - b)
    if difference >= smoothness:
        return max(a, b)
    h = (smoothness - difference) / smoothness
    return max(a, b) + h * h * smoothness * 0.25


def fuse_signed_distances(
    distances: Iterable[float], *, smoothness: float = DEFAULT_SMOOTHNESS
) -> float:
    values = tuple(require_finite(value, name="distance") for value in distances)
    if not values:
        raise ValueError("At least one signed distance is required for fusion.")
    smoothness = require_finite(smoothness, name="smoothness")
    if smoothness < 0.0:
        raise ValueError("smoothness cannot be negative.")
    result = values[0]
    for value in values[1:]:
        result = smooth_max(result, value, smoothness)
    return result


def sample_fused_sdf(
    point: NormalizedPoint,
    projections: Sequence[SDFProjection],
    *,
    symmetry_x: bool = DEFAULT_SYMMETRY_X,
    smoothness: float = DEFAULT_SMOOTHNESS,
    surface_offset: float = DEFAULT_SURFACE_OFFSET,
) -> float:
    if not projections:
        raise ValueError("At least one SDF projection is required.")
    smoothness = require_finite(smoothness, name="smoothness")
    if smoothness < 0.0:
        raise ValueError("smoothness cannot be negative.")
    surface_offset = require_finite(surface_offset, name="surface_offset")
    constraints: list[float] = []
    mirrored = (
        NormalizedPoint(x=-float(point.x), y=float(point.y), z=float(point.z))
        if symmetry_x
        else None
    )
    for projection in projections:
        if not isinstance(projection, SDFProjection):
            raise TypeError("All projections must be SDFProjection instances.")
        distance = projection.sample(point)
        if mirrored is not None:
            distance = smooth_max(distance, projection.sample(mirrored), smoothness)
        constraints.append(distance)
    return fuse_signed_distances(constraints, smoothness=smoothness) - surface_offset
