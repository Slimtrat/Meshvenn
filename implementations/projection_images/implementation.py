from __future__ import annotations

import math

from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from .context import resolve_settings
from .models import PreparedProjectionView, ProjectionImagesOutput
from .preparation import prepare_projection, projection_counts

IMPLEMENTATION_ID = "projection-images"
MINIMUM_PROJECTION_COUNT = 2


class ProjectionImagesImplementation:
    """Prepare Blender projection properties for downstream pipeline stages."""

    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.INPUT,
        label="Projection Images",
        description=(
            "Prepare enabled silhouette/RGBA views for geometry reconstruction "
            "and material projection."
        ),
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "projection-images",
            "silhouette-mask",
            "rgba-material-source",
            "arbitrary-view-angle",
            "view-weight",
            "view-alignment",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        settings = resolve_settings(context)
        if settings is None:
            return ImplementationAvailability.unavailable("Meshvenn settings are unavailable.")
        if getattr(settings, "projections", None) is None:
            return ImplementationAvailability.unavailable("Projection settings are unavailable.")

        enabled_count, ready_count = projection_counts(settings)
        details = {
            "enabled_projections": enabled_count,
            "ready_projections": ready_count,
        }
        if ready_count < MINIMUM_PROJECTION_COUNT:
            return ImplementationAvailability.unavailable(
                "At least two enabled projections with images are required.",
                details={**details, "required_projections": MINIMUM_PROJECTION_COUNT},
            )
        missing_count = enabled_count - ready_count
        if missing_count > 0:
            plural = "s" if missing_count != 1 else ""
            return ImplementationAvailability.degraded(
                f"{missing_count} enabled projection{plural} have no image and will be ignored.",
                details={**details, "missing_images": missing_count},
            )
        return ImplementationAvailability.ready_state(details=details)

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        settings = resolve_settings(context)
        if settings is None:
            return self._failure("Meshvenn settings are unavailable.")

        alpha_threshold = float(settings.alpha_threshold)
        if not math.isfinite(alpha_threshold) or not 0.0 <= alpha_threshold <= 1.0:
            return self._failure("Alpha threshold must be finite and inside [0, 1].")

        prepared_views: list[PreparedProjectionView] = []
        enabled_projection_count = 0
        missing_image_names: list[str] = []
        for projection in settings.projections:
            if not projection.enabled:
                continue
            enabled_projection_count += 1
            if projection.image is None:
                missing_image_names.append(str(projection.name))
                continue
            try:
                prepared_views.append(
                    prepare_projection(projection, alpha_threshold=alpha_threshold)
                )
            except Exception as exc:
                return self._failure(
                    f'Could not prepare projection "{projection.name}": {exc}',
                    metadata={
                        "projection": str(projection.name),
                        "exception_type": type(exc).__name__,
                    },
                )

        missing_image_count = len(missing_image_names)
        if len(prepared_views) < MINIMUM_PROJECTION_COUNT:
            return self._failure(
                "At least two enabled projections with images are required.",
                metadata={
                    "enabled_projections": enabled_projection_count,
                    "prepared_projections": len(prepared_views),
                    "missing_images": missing_image_count,
                },
            )

        output = ProjectionImagesOutput(
            views=tuple(prepared_views),
            alpha_threshold=alpha_threshold,
            enabled_projection_count=enabled_projection_count,
            missing_image_count=missing_image_count,
        )
        context.metadata["projection_view_names"] = list(output.view_names)
        context.metadata["projection_count"] = output.projection_count
        return StageExecutionResult.succeeded(
            stage=PipelineStage.INPUT,
            implementation_id=IMPLEMENTATION_ID,
            payload=output,
            message=f"Prepared {output.projection_count} projection views.",
            metrics={
                "enabled_projections": enabled_projection_count,
                "prepared_projections": output.projection_count,
                "missing_images": missing_image_count,
                "empty_masks": output.empty_mask_count,
                "mask_pixels": output.total_mask_pixels,
            },
            metadata={
                "views": [self._view_metadata(view) for view in output.views],
                "missing_image_views": missing_image_names,
                "empty_mask_views": [view.name for view in output.views if view.empty_mask],
                "alpha_threshold": alpha_threshold,
            },
        )

    @staticmethod
    def _failure(message: str, *, metadata=None) -> StageExecutionResult:
        return StageExecutionResult.failed_result(
            stage=PipelineStage.INPUT,
            implementation_id=IMPLEMENTATION_ID,
            message=message,
            metadata=metadata,
        )

    @staticmethod
    def _view_metadata(view: PreparedProjectionView) -> dict[str, object]:
        return {
            "name": view.name,
            "image": view.image_name,
            "width": view.width,
            "height": view.height,
            "azimuth_degrees": view.azimuth_degrees,
            "elevation_degrees": view.elevation_degrees,
            "flip_x": view.flip_x,
            "weight": view.weight,
            "alignment": view.alignment.as_dict(),
            "mask_pixels": view.mask_pixels,
            "empty_mask": view.empty_mask,
        }
