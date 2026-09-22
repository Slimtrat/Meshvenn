from __future__ import annotations

from typing import Any

import bpy

from ...core.geometry_contracts import GeometryProjectionSpace
from ...core.sdf import SDFBuildResult
from ...core.sdf_surface import SDFSurfaceResult
from .config import IMPLEMENTATION_ID, SDFReconstructionConfig

# =========================================================
# Height normalization
# =========================================================

def _apply_non_destructive_height_normalization(
    obj: bpy.types.Object,
    *,
    enabled: bool,
    target_height: float,
) -> float:
    """
    Apply target-height normalization through object.scale.

    Never mutate obj.data coordinates before MATERIAL.

    Projected Color and UV Bake must still be able to invert:

        local surface coordinate
            ↓
        GeometryProjectionSpace
            ↓
        normalized reconstruction coordinate
    """

    if not enabled:
        return 1.0

    if (
        not math.isfinite(
            float(
                target_height
            )
        )
        or target_height <= 0.0
    ):
        raise ValueError(
            (
                "Target height must be "
                "finite and greater than zero."
            )
        )

    current_height = float(
        obj.dimensions.z
    )

    if (
        not math.isfinite(
            current_height
        )
        or current_height <= 0.0
    ):
        return 1.0

    factor = (
        float(
            target_height
        )
        / current_height
    )

    obj.scale.x *= factor
    obj.scale.y *= factor
    obj.scale.z *= factor

    if (
        bpy.context.view_layer
        is not None
    ):
        bpy.context.view_layer.update()

    return float(
        factor
    )


# =========================================================
# Metadata
# =========================================================

def _write_geometry_metadata(
    obj: bpy.types.Object,
    *,
    source: Any,
    projection_space: GeometryProjectionSpace,
    sdf_result: SDFBuildResult,
    surface_result: SDFSurfaceResult,
    config: SDFReconstructionConfig,
    normalization_scale: float,
) -> None:
    sdf_stats = (
        sdf_result.stats
    )

    surface_stats = (
        surface_result.stats
    )

    # -----------------------------------------------------
    # Generic geometry metadata
    # -----------------------------------------------------

    obj[
        "meshvenn_geometry_implementation"
    ] = (
        IMPLEMENTATION_ID
    )

    obj[
        "meshvenn_geometry_version"
    ] = (
        IMPLEMENTATION_VERSION
    )

    obj[
        "meshvenn_geometry_backend"
    ] = (
        "python-reference"
    )

    obj[
        "meshvenn_projection_space_preserved"
    ] = True

    obj[
        "meshvenn_normalization_scale"
    ] = float(
        normalization_scale
    )

    obj[
        "meshvenn_projection_convention"
    ] = (
        projection_space
        .convention
        .value
    )

    obj[
        "meshvenn_projection_width"
    ] = (
        projection_space.width
    )

    obj[
        "meshvenn_projection_depth"
    ] = (
        projection_space.depth
    )

    obj[
        "meshvenn_projection_height"
    ] = (
        projection_space.height
    )

    obj[
        "meshvenn_projection_voxel_size"
    ] = (
        projection_space.voxel_size
    )

    obj[
        "meshvenn_projection_center_xy"
    ] = (
        projection_space.center_xy
    )

    # -----------------------------------------------------
    # SDF build
    # -----------------------------------------------------

    obj[
        "meshvenn_sdf_resolution"
    ] = (
        config.resolution
    )

    obj[
        "meshvenn_sdf_symmetry_x"
    ] = (
        config.symmetry_x
    )

    obj[
        "meshvenn_sdf_smoothness"
    ] = float(
        config.smoothness
    )

    obj[
        "meshvenn_sdf_surface_offset"
    ] = float(
        config.surface_offset
    )

    obj[
        "meshvenn_sdf_iso_level"
    ] = float(
        config.iso_level
    )

    obj[
        "meshvenn_sdf_sample_count"
    ] = (
        sdf_stats.voxel_count
    )

    obj[
        "meshvenn_sdf_projection_count"
    ] = (
        sdf_stats.projection_count
    )

    obj[
        "meshvenn_sdf_projection_samples"
    ] = (
        sdf_stats
        .projection_sample_count
    )

    obj[
        "meshvenn_sdf_min_distance"
    ] = float(
        sdf_stats
        .minimum_distance
    )

    obj[
        "meshvenn_sdf_max_distance"
    ] = float(
        sdf_stats
        .maximum_distance
    )

    obj[
        "meshvenn_sdf_inside_ratio"
    ] = float(
        sdf_stats
        .inside_ratio
    )

    # -----------------------------------------------------
    # Surface Nets
    # -----------------------------------------------------

    obj[
        "meshvenn_sdf_surface_active_cells"
    ] = (
        surface_stats
        .active_cells
    )

    obj[
        "meshvenn_sdf_surface_crossing_edges"
    ] = (
        surface_stats
        .crossing_grid_edges
    )

    obj[
        "meshvenn_sdf_surface_quads"
    ] = (
        surface_stats
        .emitted_quads
    )

    obj[
        "meshvenn_sdf_surface_boundary_skips"
    ] = (
        surface_stats
        .skipped_boundary_edges
    )

    obj[
        "meshvenn_sdf_surface_missing_cell_skips"
    ] = (
        surface_stats
        .skipped_missing_cell_edges
    )

    # -----------------------------------------------------
    # Historical BPT diagnostics
    #
    # Keep common diagnostic keys available while clearly
    # reporting a different engine.
    # -----------------------------------------------------

    obj[
        "bpt_engine"
    ] = (
        "python-sdf-reference"
    )

    obj[
        "bpt_mesh_mode"
    ] = (
        "sdf_surface_nets"
    )

    obj[
        "bpt_projection_count"
    ] = (
        sdf_stats.projection_count
    )

    obj[
        "bpt_resolution"
    ] = (
        config.resolution
    )

    obj[
        "bpt_symmetry_x"
    ] = (
        config.symmetry_x
    )

    obj[
        "bpt_voxel_size"
    ] = (
        config.voxel_size
    )

    obj[
        "bpt_center_xy"
    ] = (
        config.center_xy
    )

    obj[
        "bpt_normalize_height"
    ] = (
        config.normalize_height
    )

    if config.normalize_height:
        obj[
            "bpt_target_height"
        ] = (
            config.target_height
        )
