from __future__ import annotations

from typing import Any

from ..pipeline_contracts import PipelineContext, PipelineStage
from .surface import GeometrySurfaceOutput


def validate_geometry_surface_output(output: Any) -> GeometrySurfaceOutput:
    """
    Validate and return a generic GEOMETRY result.

    Keeping this check in one place makes failures explicit
    when an implementation accidentally returns an old,
    implementation-specific contract.
    """
    if not isinstance(output, GeometrySurfaceOutput):
        raise TypeError(
            f"GEOMETRY output must implement GeometrySurfaceOutput. Received {type(output).__name__}."
        )
    if output.blender_object is None:
        raise ValueError("GEOMETRY output contains no surface object.")
    if output.source is None:
        raise ValueError("GEOMETRY output contains no INPUT source.")
    output.projection_space.as_projection_kwargs()
    return output


def require_geometry_surface_output(context: PipelineContext) -> GeometrySurfaceOutput:
    """
    Generic typed accessor for every downstream pipeline
    stage.

    This replaces implementation-specific accessors such as:

        require_native_visual_hull_output(context)

    inside MATERIAL implementations.

    Concrete geometry code may still expose its own accessor
    for implementation-specific tooling and diagnostics.
    """
    output = context.require_output(PipelineStage.GEOMETRY)
    try:
        return validate_geometry_surface_output(output)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Pipeline GEOMETRY output is not compatible with the generic surface contract. Received {type(output).__name__}."
        ) from exc
