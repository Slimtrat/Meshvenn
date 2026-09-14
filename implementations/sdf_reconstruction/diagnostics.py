from __future__ import annotations

from typing import Any

from ...core.geometry_contracts import GeometryProjectionSpace
from ...core.pipeline_contracts import PipelineContext, PipelineStage, StageExecutionResult
from ...core.sdf import SDFBuildResult
from ...core.sdf_surface import SDFSurfaceResult
from .config import IMPLEMENTATION_ID, SDFReconstructionConfig
from .output import SDFReconstructionOutput


def finalize_geometry_output(
    *,
    context: PipelineContext,
    obj: Any,
    source: Any,
    projection_space: GeometryProjectionSpace,
    sdf_result: SDFBuildResult,
    surface_result: SDFSurfaceResult,
    config: SDFReconstructionConfig,
    normalization_scale: float,
    window_manager: Any,
) -> tuple[SDFReconstructionOutput, dict[str, Any]]:
    surface = surface_result.mesh
    # -------------------------------------------------
    # 7. Generic GEOMETRY output
    # -------------------------------------------------

    output_metrics = {
        "projection_count": (
            sdf_result
            .stats
            .projection_count
        ),

        "resolution": (
            config.resolution
        ),

        "sample_count": (
            sdf_result
            .stats
            .voxel_count
        ),

        "projection_sample_count": (
            sdf_result
            .stats
            .projection_sample_count
        ),

        "inside_ratio": (
            sdf_result
            .stats
            .inside_ratio
        ),

        "minimum_distance": (
            sdf_result
            .stats
            .minimum_distance
        ),

        "maximum_distance": (
            sdf_result
            .stats
            .maximum_distance
        ),

        "active_cells": (
            surface_result
            .stats
            .active_cells
        ),

        "crossing_grid_edges": (
            surface_result
            .stats
            .crossing_grid_edges
        ),

        "vertex_count": (
            surface
            .vertex_count
        ),

        "polygon_count": (
            surface
            .polygon_count
        ),

        "quad_count": (
            surface
            .quad_count
        ),

        "triangle_count": (
            surface
            .triangle_count
        ),

        "normalization_scale": (
            normalization_scale
        ),
    }

    output_metadata = {
        "backend": (
            "python-reference"
        ),

        "field": (
            "signed-distance"
        ),

        "surface_extractor": (
            "surface-nets"
        ),

        "sub_voxel": True,

        "symmetry_x": (
            config.symmetry_x
        ),

        "smoothness": (
            config.smoothness
        ),

        "surface_offset": (
            config.surface_offset
        ),

        "iso_level": (
            config.iso_level
        ),

        "projection_convention": (
            projection_space
            .convention
            .value
        ),

        "normalized_height": (
            config
            .normalize_height
        ),

        "target_height": (
            config.target_height
            if (
                config
                .normalize_height
            )
            else None
        ),

        "projection_space_local_coordinates_preserved": (
            True
        ),
    }

    output = (
        SDFReconstructionOutput(
            blender_object=obj,

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

            normalized_height=(
                config
                .normalize_height
            ),

            target_height=(
                config.target_height
                if (
                    config
                    .normalize_height
                )
                else None
            ),

            normalization_scale=(
                normalization_scale
            ),

            metrics=(
                output_metrics
            ),

            metadata=(
                output_metadata
            ),
        )
    )

    # -------------------------------------------------
    # Global pipeline diagnostics
    # -------------------------------------------------

    context.metadata[
        "geometry_object_name"
    ] = (
        obj.name
    )

    context.metadata[
        "geometry_implementation"
    ] = (
        IMPLEMENTATION_ID
    )

    context.metadata[
        "geometry_contract"
    ] = (
        "surface-output-v1"
    )

    context.metadata[
        "geometry_backend"
    ] = (
        "python-reference"
    )

    context.metadata[
        "geometry_mesh_mode"
    ] = (
        "sdf_surface_nets"
    )

    context.metadata[
        "geometry_sdf_resolution"
    ] = (
        config.resolution
    )

    context.metadata[
        "geometry_sdf_inside_ratio"
    ] = (
        sdf_result
        .stats
        .inside_ratio
    )

    context.metadata[
        "geometry_sdf_active_cells"
    ] = (
        surface_result
        .stats
        .active_cells
    )

    context.metadata[
        "geometry_projection_space"
    ] = {
        "width": (
            projection_space
            .width
        ),

        "depth": (
            projection_space
            .depth
        ),

        "height": (
            projection_space
            .height
        ),

        "voxel_size": (
            projection_space
            .voxel_size
        ),

        "center_xy": (
            projection_space
            .center_xy
        ),

        "convention": (
            projection_space
            .convention
            .value
        ),
    }

    if window_manager is not None:
        try:
            window_manager.progress_update(
                config.resolution
                + 4
            )

        except Exception:
            pass

    return output, output_metrics


def succeeded_geometry_result(
    *,
    obj: Any,
    output: SDFReconstructionOutput,
    output_metrics: dict[str, Any],
    projection_space: GeometryProjectionSpace,
    sdf_result: SDFBuildResult,
    surface_result: SDFSurfaceResult,
    config: SDFReconstructionConfig,
) -> StageExecutionResult:
    surface = surface_result.mesh
    # -------------------------------------------------
    # Success
    # -------------------------------------------------

    return (
        StageExecutionResult
        .succeeded(
            stage=(
                PipelineStage.GEOMETRY
            ),

            implementation_id=(
                IMPLEMENTATION_ID
            ),

            payload=output,

            message=(
                "SDF reconstruction generated: "
                f"{sdf_result.stats.voxel_count} "
                "field samples, "
                f"{surface.vertex_count} vertices, "
                f"{surface.polygon_count} quads."
            ),

            metrics=(
                output_metrics
            ),

            metadata={
                "object_name": (
                    obj.name
                ),

                "mesh_name": (
                    obj
                    .data
                    .name
                ),

                "backend": (
                    "python-reference"
                ),

                "resolution": (
                    config.resolution
                ),

                "projection_count": (
                    sdf_result
                    .stats
                    .projection_count
                ),

                "symmetry_x": (
                    config.symmetry_x
                ),

                "smoothness": (
                    config.smoothness
                ),

                "surface_offset": (
                    config.surface_offset
                ),

                "iso_level": (
                    config.iso_level
                ),

                "projection_space": {
                    "width": (
                        projection_space
                        .width
                    ),

                    "depth": (
                        projection_space
                        .depth
                    ),

                    "height": (
                        projection_space
                        .height
                    ),

                    "voxel_size": (
                        projection_space
                        .voxel_size
                    ),

                    "center_xy": (
                        projection_space
                        .center_xy
                    ),

                    "convention": (
                        projection_space
                        .convention
                        .value
                    ),
                },

                "surface": {
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

                    "missing_cell_skips": (
                        surface_result
                        .stats
                        .skipped_missing_cell_edges
                    ),
                },

                "normalize_height": (
                    config
                    .normalize_height
                ),

                "target_height": (
                    config.target_height
                    if (
                        config
                        .normalize_height
                    )
                    else None
                ),

                "projection_space_local_coordinates_preserved": (
                    True
                ),
            },
        )
    )
