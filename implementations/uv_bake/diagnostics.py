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
for _dependency in (_dependency_0, _dependency_1,):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

def _uv_layout_diagnostics(
    triangles: tuple[
        UVBakeTriangle,
        ...
    ],
    *,
    texture_size: int,
) -> UVLayoutDiagnostics:
    if not triangles:
        raise ValueError(
            (
                "Cannot inspect an empty "
                "UV triangle collection."
            )
        )

    areas = [
        float(
            triangle.absolute_uv_area
        )
        for triangle
        in triangles
    ]

    triangle_count = len(
        areas
    )

    total_uv_area = sum(
        areas
    )

    minimum_uv_area = min(
        areas
    )

    maximum_uv_area = max(
        areas
    )

    mean_uv_area = (
        total_uv_area
        / float(
            triangle_count
        )
    )

    texture_pixels = (
        float(
            texture_size
        )
        * float(
            texture_size
        )
    )

    pixel_areas = [
        area
        * texture_pixels
        for area
        in areas
    ]

    subpixel_count = sum(
        1
        for area
        in pixel_areas
        if area < 1.0
    )

    return UVLayoutDiagnostics(
        triangle_count=(
            triangle_count
        ),

        total_uv_area=(
            total_uv_area
        ),

        minimum_triangle_uv_area=(
            minimum_uv_area
        ),

        mean_triangle_uv_area=(
            mean_uv_area
        ),

        maximum_triangle_uv_area=(
            maximum_uv_area
        ),

        total_texture_area_pixels=(
            total_uv_area
            * texture_pixels
        ),

        minimum_triangle_area_pixels=(
            min(
                pixel_areas
            )
        ),

        mean_triangle_area_pixels=(
            sum(
                pixel_areas
            )
            / float(
                triangle_count
            )
        ),

        maximum_triangle_area_pixels=(
            max(
                pixel_areas
            )
        ),

        subpixel_triangle_count=(
            subpixel_count
        ),
    )


# =========================================================
# MATERIAL output
# =========================================================

@dataclass(frozen=True)
class UVBakeMaterialOutput:
    """
    MATERIAL-stage result.

    Geometry is not duplicated.

    The SAME Blender object produced by the generic GEOMETRY
    stage receives:

        UV map
        image texture
        Principled material

    geometry may originate from:

        Native Visual Hull
        SDF Reconstruction
        another future reconstruction implementation
    """

    blender_object: bpy.types.Object

    geometry: GeometrySurfaceOutput

    image: bpy.types.Image

    material: bpy.types.Material

    uv_layer_name: str

    bake_result: UVBakeResult

    config: UVBakeMaterialConfig

    @property
    def texture_size(
        self,
    ) -> int:
        return (
            self.config.texture_size
        )

    @property
    def covered_pixels(
        self,
    ) -> int:
        return (
            self.bake_result
            .stats
            .covered_pixels
        )

    @property
    def padded_pixels(
        self,
    ) -> int:
        return (
            self.bake_result
            .stats
            .padded_pixels
        )

    @property
    def coverage_ratio(
        self,
    ) -> float:
        return (
            self.bake_result
            .stats
            .coverage_ratio
        )


# =========================================================
# Context
# =========================================================
