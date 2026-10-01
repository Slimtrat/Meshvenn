"""Automatic GLB character route implementations."""

from ...core.glb_route import (
    CANONICALIZE_ROUTE,
    GEOMETRY_ONLY_ROUTE,
    GLBRouteDecision,
    PRESERVE_SOURCE_ROUTE,
    decide_glb_character_route,
)
from .geometry import GLBAutoGeometryImplementation, resolve_glb_route
from .motion import GLBAutoMotionImplementation
from .rig import GLBAutoRigImplementation

__all__ = (
    "CANONICALIZE_ROUTE",
    "GEOMETRY_ONLY_ROUTE",
    "GLBAutoGeometryImplementation",
    "GLBAutoMotionImplementation",
    "GLBAutoRigImplementation",
    "GLBRouteDecision",
    "PRESERVE_SOURCE_ROUTE",
    "decide_glb_character_route",
    "resolve_glb_route",
)
