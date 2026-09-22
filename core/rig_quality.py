"""Conservative, engine-neutral diagnostics for Canonical Biped V1 geometry.

The canonical fit uses a Z-up bounding box and always places a symmetric
skeleton. These measurements describe that box and its vertex distribution;
they do *not* identify limbs, infer anatomy, or certify that skinning will work.

Thresholds are deliberately broad heuristics, not acceptance criteria:
height/width outside [0.65, 5.0], a lateral envelope imbalance above 0.45,
or bilateral vertex coverage below 0.30 produces a non-blocking warning.
The envelope uses the 90th percentile of each side's distance from the bounds
midline, so an isolated extremal vertex does not define the whole side.
Coverage ignores vertices within 2% of the bounds width around that midline.
Uneven tessellation can affect both measurements, even on symmetric anatomy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .canonical_rig import MeshBounds


_CENTERLINE_FRACTION = 0.02
_ENVELOPE_PERCENTILE = 0.90
_MIN_HEIGHT_TO_WIDTH = 0.65
_MAX_HEIGHT_TO_WIDTH = 5.0
_MAX_ENVELOPE_IMBALANCE = 0.45
_MIN_BILATERAL_COVERAGE = 0.30


@dataclass(frozen=True)
class RigGeometryAssessment:
    """JSON-serializable measurements and non-blocking diagnostic codes."""

    vertex_count: int
    height_to_width: float
    left_envelope_radius: float
    right_envelope_radius: float
    left_right_envelope_imbalance: float
    left_vertex_count: int
    right_vertex_count: int
    bilateral_vertex_coverage: float
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Return the stable V1 wire shape using only JSON-native values."""

        return {
            "schema_version": 1,
            "vertex_count": self.vertex_count,
            "height_to_width": self.height_to_width,
            "left_envelope_radius": self.left_envelope_radius,
            "right_envelope_radius": self.right_envelope_radius,
            "left_right_envelope_imbalance": self.left_right_envelope_imbalance,
            "left_vertex_count": self.left_vertex_count,
            "right_vertex_count": self.right_vertex_count,
            "bilateral_vertex_coverage": self.bilateral_vertex_coverage,
            "warnings": list(self.warnings),
        }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = fraction * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def assess_biped_geometry(
    vertices: Iterable[Sequence[float]], bounds: MeshBounds
) -> RigGeometryAssessment:
    """Assess geometric fit risks without rejecting a stylized biped.

    ``bounds`` and vertices must be expressed in the same Z-up mesh-local
    coordinates. Anatomical left is +X, matching ``fit_canonical_biped``.
    Vertices may be a one-shot iterator; it is consumed exactly once.
    """

    if not isinstance(bounds, MeshBounds):
        raise TypeError("bounds must be a MeshBounds instance.")
    width, height, center_x = bounds.width, bounds.height, bounds.center_x
    if not all(math.isfinite(value) for value in (width, height, center_x)):
        raise ValueError("Mesh dimensions and center must be finite.")
    height_to_width = height / width
    if not math.isfinite(height_to_width):
        raise ValueError("Mesh height-to-width ratio must be finite.")

    tolerance = _CENTERLINE_FRACTION * width
    left_distances: list[float] = []
    right_distances: list[float] = []
    count = 0
    for vertex in vertices:
        point = tuple(float(value) for value in vertex)
        if len(point) != 3 or any(not math.isfinite(value) for value in point):
            raise ValueError("Mesh vertices must contain three finite coordinates.")
        count += 1
        lateral_distance = point[0] - center_x
        if lateral_distance > tolerance:
            left_distances.append(lateral_distance)
        elif lateral_distance < -tolerance:
            right_distances.append(-lateral_distance)
    if count == 0:
        raise ValueError("Cannot assess an empty mesh.")

    left_radius = _percentile(left_distances, _ENVELOPE_PERCENTILE)
    right_radius = _percentile(right_distances, _ENVELOPE_PERCENTILE)
    radius_sum = left_radius + right_radius
    envelope_imbalance = abs(left_radius - right_radius) / radius_sum if radius_sum else 0.0
    side_count = len(left_distances) + len(right_distances)
    bilateral_coverage = (
        2.0 * min(len(left_distances), len(right_distances)) / side_count
        if side_count else 0.0
    )

    warnings: list[str] = []
    if height_to_width < _MIN_HEIGHT_TO_WIDTH:
        warnings.append("low_height_to_width")
    elif height_to_width > _MAX_HEIGHT_TO_WIDTH:
        warnings.append("high_height_to_width")
    if envelope_imbalance > _MAX_ENVELOPE_IMBALANCE:
        warnings.append("left_right_envelope_imbalance")
    if bilateral_coverage < _MIN_BILATERAL_COVERAGE:
        warnings.append("low_bilateral_vertex_coverage")
    return RigGeometryAssessment(
        vertex_count=count,
        height_to_width=height_to_width,
        left_envelope_radius=left_radius,
        right_envelope_radius=right_radius,
        left_right_envelope_imbalance=envelope_imbalance,
        left_vertex_count=len(left_distances),
        right_vertex_count=len(right_distances),
        bilateral_vertex_coverage=bilateral_coverage,
        warnings=tuple(warnings),
    )
