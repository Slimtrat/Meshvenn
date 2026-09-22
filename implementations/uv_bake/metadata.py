from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any

import bpy

from ...core.geometry_contracts import (
    GeometrySurfaceOutput,
    require_geometry_surface_output,
)
from ...core.material_blend import (
    MaterialBlendConfig,
)
from ...core.material_visibility import (
    MeshVisibilityTester,
)
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.projected_material import (
    DEFAULT_FALLBACK_COLOR,
    blend_projected_color,
)
from ...core.uv_bake import (
    SurfaceColorSample,
    UVBakeConfig,
    UVBakeResult,
    UVBakeTriangle,
    UVBakeVertex,
    bake_uv_texture,
)

from . import constants as _dependency_0
from . import config as _dependency_1
from . import diagnostics as _dependency_2
from . import settings as _dependency_3
from . import geometry as _dependency_4
from . import triangles as _dependency_5
from . import sampler as _dependency_6
from . import assets as _dependency_7
for _dependency in (_dependency_0, _dependency_1, _dependency_2, _dependency_3, _dependency_4, _dependency_5, _dependency_6, _dependency_7,):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

def _assign_material(
    obj: bpy.types.Object,
    material: bpy.types.Material,
) -> None:
    mesh = (
        obj.data
    )

    mesh.materials.clear()

    mesh.materials.append(
        material
    )


# =========================================================
# Metadata
# =========================================================

def _write_metadata(
    obj: bpy.types.Object,
    output: UVBakeMaterialOutput,
    *,
    layout: UVLayoutDiagnostics,
) -> None:
    stats = (
        output
        .bake_result
        .stats
    )

    config = (
        output.config
    )

    geometry = (
        output.geometry
    )

    projection_space = (
        geometry
        .projection_space
    )

    # -----------------------------------------------------
    # Material identity
    # -----------------------------------------------------

    obj[
        "meshvenn_material_implementation"
    ] = (
        IMPLEMENTATION_ID
    )

    obj[
        "meshvenn_material_version"
    ] = "2"

    obj[
        "meshvenn_material_mode"
    ] = (
        MATERIAL_MODE
    )

    obj[
        "meshvenn_material_geometry_implementation"
    ] = (
        geometry
        .implementation_id
    )

    obj[
        "meshvenn_material_projection_convention"
    ] = (
        projection_space
        .convention
        .value
    )

    # -----------------------------------------------------
    # UV / image
    # -----------------------------------------------------

    obj[
        "meshvenn_uv_layer"
    ] = (
        output.uv_layer_name
    )

    obj[
        "meshvenn_uv_bake_image"
    ] = (
        output.image.name
    )

    obj[
        "meshvenn_uv_bake_material"
    ] = (
        output.material.name
    )

    obj[
        "meshvenn_uv_bake_texture_size"
    ] = (
        config.texture_size
    )

    obj[
        "meshvenn_uv_bake_padding"
    ] = (
        config.padding_pixels
    )

    obj[
        "meshvenn_uv_bake_samples_per_axis"
    ] = (
        config.samples_per_axis
    )

    # -----------------------------------------------------
    # Projection-space diagnostics
    # -----------------------------------------------------

    obj[
        "meshvenn_uv_projection_width"
    ] = (
        projection_space.width
    )

    obj[
        "meshvenn_uv_projection_depth"
    ] = (
        projection_space.depth
    )

    obj[
        "meshvenn_uv_projection_height"
    ] = (
        projection_space.height
    )

    obj[
        "meshvenn_uv_projection_voxel_size"
    ] = (
        projection_space
        .voxel_size
    )

    obj[
        "meshvenn_uv_projection_center_xy"
    ] = (
        projection_space
        .center_xy
    )

    # -----------------------------------------------------
    # Smart Project diagnostics
    # -----------------------------------------------------

    obj[
        "meshvenn_uv_requested_island_margin_fraction"
    ] = float(
        config.island_margin
    )

    obj[
        "meshvenn_uv_effective_island_margin_fraction"
    ] = float(
        config
        .effective_island_margin_fraction
    )

    obj[
        "meshvenn_uv_effective_island_margin_pixels"
    ] = float(
        config
        .effective_island_margin_pixels
    )

    # -----------------------------------------------------
    # UV layout diagnostics
    # -----------------------------------------------------

    obj[
        "meshvenn_uv_total_area"
    ] = float(
        layout.total_uv_area
    )

    obj[
        "meshvenn_uv_total_area_pixels"
    ] = float(
        layout
        .total_texture_area_pixels
    )

    obj[
        "meshvenn_uv_mean_triangle_area_pixels"
    ] = float(
        layout
        .mean_triangle_area_pixels
    )

    obj[
        "meshvenn_uv_subpixel_triangle_count"
    ] = int(
        layout
        .subpixel_triangle_count
    )

    obj[
        "meshvenn_uv_subpixel_triangle_ratio"
    ] = float(
        layout
        .subpixel_triangle_ratio
    )

    # -----------------------------------------------------
    # Bake diagnostics
    # -----------------------------------------------------

    obj[
        "meshvenn_uv_bake_triangles"
    ] = (
        stats.triangle_count
    )

    obj[
        "meshvenn_uv_bake_covered_pixels"
    ] = (
        stats.covered_pixels
    )

    obj[
        "meshvenn_uv_bake_padded_pixels"
    ] = (
        stats.padded_pixels
    )

    obj[
        "meshvenn_uv_bake_overlap_pixels"
    ] = (
        stats.overlap_pixels
    )

    obj[
        "meshvenn_uv_bake_surface_samples"
    ] = (
        stats.surface_samples
    )

    obj[
        "meshvenn_uv_bake_fallback_samples"
    ] = (
        stats.fallback_samples
    )

    obj[
        "meshvenn_uv_bake_coverage_ratio"
    ] = float(
        stats.coverage_ratio
    )


# =========================================================
# UI
# =========================================================
