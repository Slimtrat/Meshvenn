"""Stable public facade for projection-space mathematics."""

from .coordinates import grid_to_normalized, surface_position_to_normalized
from .models import EPSILON, NormalizedPoint, ProjectedPoint, ProjectionTransform
from .projection import (
    compile_projection,
    direction_to_camera,
    project_normalized_point,
    project_surface_position,
)
from .vectors import clamp01, dot3, normalize3

__all__ = (
    "EPSILON", "NormalizedPoint", "ProjectedPoint", "ProjectionTransform",
    "grid_to_normalized", "surface_position_to_normalized", "compile_projection",
    "project_normalized_point", "project_surface_position", "direction_to_camera",
    "clamp01", "dot3", "normalize3",
)
