"""Stable public geometry contracts, split by responsibility."""

from .projection import (
    DEFAULT_PROJECTION_CONVENTION,
    GeometryProjectionConvention,
    GeometryProjectionSpace,
)
from .surface import GeometrySurfaceOutput
from .validation import (
    require_geometry_surface_output,
    validate_geometry_surface_output,
)

__all__ = (
    "DEFAULT_PROJECTION_CONVENTION",
    "GeometryProjectionConvention",
    "GeometryProjectionSpace",
    "GeometrySurfaceOutput",
    "require_geometry_surface_output",
    "validate_geometry_surface_output",
)
