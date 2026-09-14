from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any

import bpy

from ..core.geometry_contracts import (
    GeometrySurfaceOutput,
    require_geometry_surface_output,
)
from ..core.material_blend import (
    MaterialBlendConfig,
)
from ..core.material_visibility import (
    MeshVisibilityTester,
)
from ..core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..core.projected_material import (
    DEFAULT_FALLBACK_COLOR,
    blend_projected_color,
)
from ..core.uv_bake import (
    SurfaceColorSample,
    UVBakeConfig,
    UVBakeResult,
    UVBakeTriangle,
    UVBakeVertex,
    bake_uv_texture,
)

from . import constants as _dependency_0
for _dependency in (_dependency_0,):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

@dataclass(frozen=True)
class UVBakeMaterialConfig:
    texture_size: int = (
        DEFAULT_TEXTURE_SIZE
    )

    padding_pixels: int = (
        DEFAULT_PADDING_PIXELS
    )

    samples_per_axis: int = (
        DEFAULT_SAMPLES_PER_AXIS
    )

    uv_layer_name: str = (
        DEFAULT_UV_LAYER_NAME
    )

    island_margin: float = (
        DEFAULT_ISLAND_MARGIN
    )

    angle_limit_degrees: float = (
        DEFAULT_ANGLE_LIMIT_DEGREES
    )

    reuse_existing_uv: bool = (
        DEFAULT_REUSE_EXISTING_UV
    )

    enable_visibility: bool = (
        DEFAULT_ENABLE_VISIBILITY
    )

    allow_backface_fallback: bool = (
        DEFAULT_ALLOW_BACKFACE_FALLBACK
    )

    min_facing: float = (
        DEFAULT_MIN_FACING
    )

    facing_power: float = (
        DEFAULT_FACING_POWER
    )

    relative_score_cutoff: float = (
        DEFAULT_RELATIVE_SCORE_CUTOFF
    )

    max_contributors: int = (
        DEFAULT_MAX_CONTRIBUTORS
    )

    weight_power: float = (
        DEFAULT_WEIGHT_POWER
    )

    def validate(
        self,
    ) -> None:
        if self.texture_size <= 0:
            raise ValueError(
                (
                    "Texture size must "
                    "be positive."
                )
            )

        if (
            not self.uv_layer_name
            or not self
            .uv_layer_name
            .strip()
        ):
            raise ValueError(
                (
                    "UV layer name cannot "
                    "be empty."
                )
            )

        if (
            not math.isfinite(
                self.island_margin
            )
            or self.island_margin < 0.0
            or self.island_margin > 1.0
        ):
            raise ValueError(
                (
                    "Island margin must "
                    "be in [0, 1]."
                )
            )

        if (
            not math.isfinite(
                self.angle_limit_degrees
            )
            or self.angle_limit_degrees
            <= 0.0
            or self.angle_limit_degrees
            > 90.0
        ):
            raise ValueError(
                (
                    "Smart-project angle limit "
                    "must be inside ]0, 90]."
                )
            )

        self.to_bake_config().validate()

        self.to_blend_config().validate()

    def to_bake_config(
        self,
    ) -> UVBakeConfig:
        return UVBakeConfig(
            width=(
                self.texture_size
            ),
            height=(
                self.texture_size
            ),
            padding_pixels=(
                self.padding_pixels
            ),
            samples_per_axis=(
                self.samples_per_axis
            ),
            background_color=(
                0.0,
                0.0,
                0.0,
                0.0,
            ),
            clamp_colors=True,
        )

    def to_blend_config(
        self,
    ) -> MaterialBlendConfig:
        return MaterialBlendConfig(
            min_facing=(
                self.min_facing
            ),
            facing_power=(
                self.facing_power
            ),
            relative_score_cutoff=(
                self.relative_score_cutoff
            ),
            max_contributors=(
                self.max_contributors
            ),
            weight_power=(
                self.weight_power
            ),
        )

    @property
    def maximum_smart_project_margin_fraction(
        self,
    ) -> float:
        return (
            MAX_SMART_PROJECT_MARGIN_TEXELS
            / float(
                self.texture_size
            )
        )

    @property
    def effective_island_margin_fraction(
        self,
    ) -> float:
        return min(
            float(
                self.island_margin
            ),
            self
            .maximum_smart_project_margin_fraction,
        )

    @property
    def effective_island_margin_pixels(
        self,
    ) -> float:
        return (
            self
            .effective_island_margin_fraction
            * float(
                self.texture_size
            )
        )


# =========================================================
# UV diagnostics
# =========================================================

@dataclass(frozen=True)
class UVLayoutDiagnostics:
    triangle_count: int

    total_uv_area: float

    minimum_triangle_uv_area: float

    mean_triangle_uv_area: float

    maximum_triangle_uv_area: float

    total_texture_area_pixels: float

    minimum_triangle_area_pixels: float

    mean_triangle_area_pixels: float

    maximum_triangle_area_pixels: float

    subpixel_triangle_count: int

    @property
    def subpixel_triangle_ratio(
        self,
    ) -> float:
        if self.triangle_count <= 0:
            return 0.0

        return (
            float(
                self.subpixel_triangle_count
            )
            / float(
                self.triangle_count
            )
        )
