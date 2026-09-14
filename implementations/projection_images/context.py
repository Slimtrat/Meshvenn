from __future__ import annotations

from typing import Any

from ...core.pipeline_contracts import PipelineContext, PipelineStage
from .models import ProjectionImagesOutput


def resolve_settings(context: PipelineContext) -> Any:
    """Resolve settings without importing the Blender property module."""

    if context.settings is not None:
        return context.settings
    if context.scene is None:
        return None
    return getattr(context.scene, "bpt_settings", None)


def require_projection_images_output(context: PipelineContext) -> ProjectionImagesOutput:
    output = context.require_output(PipelineStage.INPUT)
    if not isinstance(output, ProjectionImagesOutput):
        raise TypeError(
            "INPUT output is incompatible with \"projection-images\". Expected "
            f"ProjectionImagesOutput, received {type(output).__name__}."
        )
    return output
