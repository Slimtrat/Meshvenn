from __future__ import annotations

from .domain import Vector3, DEFAULT_RELATIVE_EPSILON, DEFAULT_ABSOLUTE_EPSILON, DEFAULT_RAY_LENGTH_MULTIPLIER, MIN_DIRECTION_LENGTH, MIN_RAY_DISTANCE, RaycastHit, RaycastFunction, VisibilityConfig, VisibilityResult, bounding_box_diagonal, compute_surface_epsilon, compute_ray_distance
from .tester import MeshVisibilityTester


def _build_blender_bvh_raycast(vertices, polygons):
    """Preserve the legacy callback while loading Blender's adapter on demand."""
    from .blender_backend import _build_blender_bvh_raycast as build
    return build(vertices, polygons)

__all__ = ["Vector3", "DEFAULT_RELATIVE_EPSILON", "DEFAULT_ABSOLUTE_EPSILON", "DEFAULT_RAY_LENGTH_MULTIPLIER", "MIN_DIRECTION_LENGTH", "MIN_RAY_DISTANCE", "RaycastHit", "RaycastFunction", "VisibilityConfig", "VisibilityResult", "bounding_box_diagonal", "compute_surface_epsilon", "compute_ray_distance", "MeshVisibilityTester"]
