from __future__ import annotations

from dataclasses import dataclass

EPSILON = 1e-9


@dataclass(frozen=True)
class NormalizedPoint:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class ProjectedPoint:
    u: float
    v: float

    @property
    def inside(self) -> bool:
        return 0.0 <= self.u <= 1.0 and 0.0 <= self.v <= 1.0


@dataclass(frozen=True)
class ProjectionTransform:
    """Precompiled transform matching the native C++ projection convention."""

    azimuth_degrees: float
    elevation_degrees: float
    cos_az: float
    sin_az: float
    cos_el: float
    sin_el: float
    horizontal_extent: float
    vertical_extent: float
    flip_x: bool
