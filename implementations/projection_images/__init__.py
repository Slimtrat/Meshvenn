"""Stable facade for the built-in projection-images input adapter."""

from .context import require_projection_images_output
from .implementation import (
    IMPLEMENTATION_ID,
    MINIMUM_PROJECTION_COUNT,
    ProjectionImagesImplementation,
)
from .models import PreparedProjectionView, ProjectionImagesOutput

__all__ = (
    "IMPLEMENTATION_ID",
    "MINIMUM_PROJECTION_COUNT",
    "PreparedProjectionView",
    "ProjectionImagesOutput",
    "ProjectionImagesImplementation",
    "require_projection_images_output",
)
