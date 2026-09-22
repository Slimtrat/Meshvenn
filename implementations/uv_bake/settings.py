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
for _dependency in (_dependency_0, _dependency_1, _dependency_2,):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

def _resolve_settings(
    context: PipelineContext,
) -> Any:
    if context.settings is not None:
        return context.settings

    if context.scene is None:
        return None

    return getattr(
        context.scene,
        "bpt_settings",
        None,
    )


def require_uv_bake_output(
    context: PipelineContext,
) -> UVBakeMaterialOutput:
    output = (
        context.require_output(
            PipelineStage.MATERIAL
        )
    )

    if not isinstance(
        output,
        UVBakeMaterialOutput,
    ):
        raise TypeError(
            (
                "MATERIAL output is not "
                "UVBakeMaterialOutput. "
                "Received "
                f"{type(output).__name__}."
            )
        )

    return output


# =========================================================
# Settings
# =========================================================

def _read_setting(
    settings: Any,
    name: str,
    default: Any,
) -> Any:
    if settings is None:
        return default

    return getattr(
        settings,
        name,
        default,
    )


def _config_from_settings(
    settings: Any,
) -> UVBakeMaterialConfig:
    config = (
        UVBakeMaterialConfig(
            texture_size=int(
                _read_setting(
                    settings,
                    "uv_bake_texture_size",
                    DEFAULT_TEXTURE_SIZE,
                )
            ),

            padding_pixels=int(
                _read_setting(
                    settings,
                    "uv_bake_padding_pixels",
                    DEFAULT_PADDING_PIXELS,
                )
            ),

            samples_per_axis=int(
                _read_setting(
                    settings,
                    "uv_bake_samples_per_axis",
                    DEFAULT_SAMPLES_PER_AXIS,
                )
            ),

            uv_layer_name=str(
                _read_setting(
                    settings,
                    "uv_bake_uv_layer_name",
                    DEFAULT_UV_LAYER_NAME,
                )
            ).strip(),

            island_margin=float(
                _read_setting(
                    settings,
                    "uv_bake_island_margin",
                    DEFAULT_ISLAND_MARGIN,
                )
            ),

            angle_limit_degrees=float(
                _read_setting(
                    settings,
                    "uv_bake_angle_limit_degrees",
                    DEFAULT_ANGLE_LIMIT_DEGREES,
                )
            ),

            reuse_existing_uv=bool(
                _read_setting(
                    settings,
                    "uv_bake_reuse_existing_uv",
                    DEFAULT_REUSE_EXISTING_UV,
                )
            ),

            enable_visibility=bool(
                _read_setting(
                    settings,
                    "material_enable_visibility",
                    DEFAULT_ENABLE_VISIBILITY,
                )
            ),

            allow_backface_fallback=bool(
                _read_setting(
                    settings,
                    "material_allow_backface_fallback",
                    DEFAULT_ALLOW_BACKFACE_FALLBACK,
                )
            ),

            min_facing=float(
                _read_setting(
                    settings,
                    "material_min_facing",
                    DEFAULT_MIN_FACING,
                )
            ),

            facing_power=float(
                _read_setting(
                    settings,
                    "material_facing_power",
                    DEFAULT_FACING_POWER,
                )
            ),

            relative_score_cutoff=float(
                _read_setting(
                    settings,
                    "material_relative_score_cutoff",
                    DEFAULT_RELATIVE_SCORE_CUTOFF,
                )
            ),

            max_contributors=int(
                _read_setting(
                    settings,
                    "material_max_contributors",
                    DEFAULT_MAX_CONTRIBUTORS,
                )
            ),

            weight_power=float(
                _read_setting(
                    settings,
                    "material_weight_power",
                    DEFAULT_WEIGHT_POWER,
                )
            ),
        )
    )

    config.validate()

    return config


# =========================================================
# Source capability
# =========================================================

def _material_views_from_geometry(
    geometry: GeometrySurfaceOutput,
) -> tuple[
    Any,
    ...
]:
    """
    UV Bake requires source projection-color views.

    It deliberately does not care which INPUT implementation
    produced those views.

    Required capability:

        geometry.source.material_views
    """

    source = (
        geometry.source
    )

    material_views = getattr(
        source,
        "material_views",
        None,
    )

    if material_views is None:
        raise TypeError(
            (
                "GEOMETRY source does not expose "
                "material_views required by "
                "UV Bake V2."
            )
        )

    try:
        resolved = tuple(
            material_views
        )

    except TypeError as exc:
        raise TypeError(
            (
                "GEOMETRY source material_views "
                "is not iterable."
            )
        ) from exc

    if not resolved:
        raise ValueError(
            (
                "No source material views "
                "are available."
            )
        )

    return resolved


# =========================================================
# Geometry validation
# =========================================================
