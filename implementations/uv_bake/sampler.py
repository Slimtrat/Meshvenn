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
for _dependency in (_dependency_0, _dependency_1, _dependency_2, _dependency_3, _dependency_4, _dependency_5,):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

def _build_surface_sampler(
    geometry: GeometrySurfaceOutput,
    config: UVBakeMaterialConfig,
    *, views=None, diagnostics=False,
):
    """
    Build the Projected Color V1.2 surface sampler used by
    UV Bake.

    Important:

    this function only depends on the generic GEOMETRY
    contract.

    It knows nothing about:

        NativeVisualHullOutput
        NativeVolume
        SDFVolume
        reconstruction implementation internals
    """

    views = list(views) if views is not None else list(
        _material_views_from_geometry(
            geometry
        )
    )

    blend_config = (
        config.to_blend_config()
    )

    projection_space = (
        geometry
        .projection_space
    )

    visibility_tester = None

    if config.enable_visibility:
        # Build one BVH for the complete bake.

        visibility_tester = (
            MeshVisibilityTester
            .from_blender_object(
                geometry
                .blender_object,
                use_loop_triangles=True,
            )
        )

    counters = {name: 0 for name in (
        "total_samples", "candidate_samples", "source_rejected_samples", "visible_samples",
        "occluded_samples", "front_facing_samples", "backface_samples", "grazing_rejected_samples",
        "primary_samples", "projected_fallback_samples", "neutral_fallback_samples", "selected_samples")}
    def sample_surface(
        position,
        normal,
    ) -> SurfaceColorSample:
        if diagnostics:
            from ...core.projected_material.blending import _blend_projected_color_detailed
            result = _blend_projected_color_detailed(
                position, normal, views, **projection_space.as_projection_kwargs(),
                facing_power=config.facing_power, fallback_color=DEFAULT_FALLBACK_COLOR,
                allow_backface_fallback=config.allow_backface_fallback,
                visibility_tester=visibility_tester, blend_config=blend_config)
            for name in ("total_samples", "candidate_samples", "source_rejected_samples",
                         "visible_samples", "occluded_samples", "front_facing_samples",
                         "backface_samples", "grazing_rejected_samples", "selected_samples"):
                counters[name] = counters.get(name, 0) + getattr(result, name)
            kind = ("neutral_fallback_samples" if not result.selected_samples else
                    "projected_fallback_samples" if result.used_fallback else "primary_samples")
            counters[kind] = counters.get(kind, 0) + 1
            return SurfaceColorSample(color=result.color, used_fallback=result.used_fallback,
                                      selected_samples=result.selected_samples)
        (
            color,
            accepted_samples,
            _rejected_samples,
            used_fallback,
        ) = (
            blend_projected_color(
                position,
                normal,
                views,

                width=(
                    projection_space
                    .width
                ),

                depth=(
                    projection_space
                    .depth
                ),

                height=(
                    projection_space
                    .height
                ),

                voxel_size=(
                    projection_space
                    .voxel_size
                ),

                center_xy=(
                    projection_space
                    .center_xy
                ),

                facing_power=(
                    config
                    .facing_power
                ),

                fallback_color=(
                    DEFAULT_FALLBACK_COLOR
                ),

                allow_backface_fallback=(
                    config
                    .allow_backface_fallback
                ),

                visibility_tester=(
                    visibility_tester
                ),

                blend_config=(
                    blend_config
                ),
            )
        )

        return SurfaceColorSample(
            color=(
                color
            ),

            used_fallback=(
                used_fallback
            ),

            selected_samples=(
                accepted_samples
            ),
        )

    sample_surface.diagnostics = counters
    return sample_surface


# =========================================================
# Blender image
# =========================================================
