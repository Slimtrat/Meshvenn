from __future__ import annotations

from ...core.pipeline_contracts import PipelineContext, PipelineStage, StageExecutionResult
from ...core.sdf import SDFBuildProgress, build_sdf_from_views
from ...core.sdf_surface import extract_surface_nets
from .blender_mesh import _create_blender_surface, _projection_space_from_config, _remove_blender_object
from .config import IMPLEMENTATION_ID
from .diagnostics import finalize_geometry_output, succeeded_geometry_result
from .metadata import _apply_non_destructive_height_normalization, _write_geometry_metadata
from .output import SDFReconstructionOutput
from .resolution import _config_from_settings, _require_input_source, _resolve_settings, _source_views


def execute_sdf_reconstruction(
    context: PipelineContext,
) -> StageExecutionResult:
    settings = (
        _resolve_settings(
            context
        )
    )

    if settings is None:
        return (
            StageExecutionResult
            .failed_result(
                stage=(
                    PipelineStage.GEOMETRY
                ),

                implementation_id=(
                    IMPLEMENTATION_ID
                ),

                message=(
                    "Meshvenn settings "
                    "are unavailable."
                ),
            )
        )

    try:
        source = (
            _require_input_source(
                context
            )
        )

        views = (
            _source_views(
                source
            )
        )

    except Exception as exc:
        return (
            StageExecutionResult
            .failed_result(
                stage=(
                    PipelineStage.GEOMETRY
                ),

                implementation_id=(
                    IMPLEMENTATION_ID
                ),

                message=(
                    "Prepared silhouette input "
                    f"is unavailable: {exc}"
                ),
            )
        )

    try:
        config = (
            _config_from_settings(
                settings
            )
        )

    except Exception as exc:
        return (
            StageExecutionResult
            .failed_result(
                stage=(
                    PipelineStage.GEOMETRY
                ),

                implementation_id=(
                    IMPLEMENTATION_ID
                ),

                message=(
                    "Invalid SDF Reconstruction "
                    f"configuration: {exc}"
                ),

                metadata={
                    "exception_type": (
                        type(
                            exc
                        )
                        .__name__
                    ),
                },
            )
        )

    obj: (
        bpy.types.Object
        | None
    ) = None

    window_manager = getattr(
        bpy.context,
        "window_manager",
        None,
    )

    progress_active = False

    try:
        if window_manager is not None:
            try:
                window_manager.progress_begin(
                    0,
                    (
                        config.resolution
                        + 4
                    ),
                )

                progress_active = True

            except Exception:
                window_manager = None

        # -------------------------------------------------
        # 1. Build continuous SDF
        # -------------------------------------------------

        def sdf_progress(
            progress: SDFBuildProgress,
        ) -> None:
            if window_manager is None:
                return

            try:
                window_manager.progress_update(
                    progress
                    .completed_slices
                )

            except Exception:
                pass

        try:
            sdf_result = (
                build_sdf_from_views(
                    views,

                    config=(
                        config
                        .to_build_config()
                    ),

                    progress_callback=(
                        sdf_progress
                    ),
                )
            )

        except Exception as exc:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),

                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),

                    message=(
                        "SDF field construction "
                        f"failed: {exc}"
                    ),

                    metadata={
                        "resolution": (
                            config.resolution
                        ),

                        "projection_count": len(
                            views
                        ),

                        "backend": (
                            "python-reference"
                        ),
                    },
                )
            )

        if window_manager is not None:
            try:
                window_manager.progress_update(
                    config.resolution
                    + 1
                )

            except Exception:
                pass

        # -------------------------------------------------
        # Field must contain both sides of the iso-surface.
        # -------------------------------------------------

        if not (
            sdf_result
            .volume
            .crosses_surface
        ):
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),

                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),

                    message=(
                        "SDF field does not cross "
                        "the requested iso-surface."
                    ),

                    metadata={
                        "minimum_distance": (
                            sdf_result
                            .volume
                            .minimum_value
                        ),

                        "maximum_distance": (
                            sdf_result
                            .volume
                            .maximum_value
                        ),

                        "iso_level": (
                            config.iso_level
                        ),

                        "inside_ratio": (
                            sdf_result
                            .stats
                            .inside_ratio
                        ),
                    },
                )
            )

        # -------------------------------------------------
        # 2. Continuous Surface Nets
        # -------------------------------------------------

        try:
            surface_result = (
                extract_surface_nets(
                    sdf_result.volume,

                    config=(
                        config
                        .to_surface_config()
                    ),
                )
            )

        except Exception as exc:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),

                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),

                    message=(
                        "SDF Surface Nets "
                        f"extraction failed: {exc}"
                    ),
                )
            )

        surface = (
            surface_result.mesh
        )

        if (
            surface.vertex_count <= 0
            or surface.polygon_count <= 0
        ):
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),

                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),

                    message=(
                        "SDF extraction produced "
                        "an empty surface mesh."
                    ),

                    metadata={
                        "active_cells": (
                            surface_result
                            .stats
                            .active_cells
                        ),

                        "crossing_edges": (
                            surface_result
                            .stats
                            .crossing_grid_edges
                        ),

                        "boundary_skips": (
                            surface_result
                            .stats
                            .skipped_boundary_edges
                        ),
                    },
                )
            )

        if window_manager is not None:
            try:
                window_manager.progress_update(
                    config.resolution
                    + 2
                )

            except Exception:
                pass

        # -------------------------------------------------
        # 3. Generic projection coordinate space
        # -------------------------------------------------

        projection_space = (
            _projection_space_from_config(
                config
            )
        )

        # -------------------------------------------------
        # 4. Blender mesh
        # -------------------------------------------------

        obj = (
            _create_blender_surface(
                surface_result,
                projection_space,
            )
        )

        if window_manager is not None:
            try:
                window_manager.progress_update(
                    config.resolution
                    + 3
                )

            except Exception:
                pass

        # -------------------------------------------------
        # 5. Non-destructive output normalization
        # -------------------------------------------------

        normalization_scale = (
            _apply_non_destructive_height_normalization(
                obj,

                enabled=(
                    config
                    .normalize_height
                ),

                target_height=(
                    config
                    .target_height
                ),
            )
        )

        # -------------------------------------------------
        # 6. Metadata
        # -------------------------------------------------

        _write_geometry_metadata(
            obj,

            source=source,

            projection_space=(
                projection_space
            ),

            sdf_result=(
                sdf_result
            ),

            surface_result=(
                surface_result
            ),

            config=config,

            normalization_scale=(
                normalization_scale
            ),
        )

        output, output_metrics = finalize_geometry_output(
            context=context,
            obj=obj,
            source=source,
            projection_space=projection_space,
            sdf_result=sdf_result,
            surface_result=surface_result,
            config=config,
            normalization_scale=normalization_scale,
            window_manager=window_manager,
        )

        return succeeded_geometry_result(
            obj=obj,
            output=output,
            output_metrics=output_metrics,
            projection_space=projection_space,
            sdf_result=sdf_result,
            surface_result=surface_result,
            config=config,
        )

    except Exception:
        # -------------------------------------------------
        # Any Blender object created by a failed GEOMETRY
        # stage must not leak into the scene.
        # -------------------------------------------------

        _remove_blender_object(
            obj
        )

        raise

    finally:
        if (
            progress_active
            and window_manager
            is not None
        ):
            try:
                window_manager.progress_end()

            except Exception:
                pass
