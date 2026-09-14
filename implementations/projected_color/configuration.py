from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any
from ...core.geometry_contracts import GeometrySurfaceOutput
from ...core.material_blend import MaterialBlendConfig
from ...core.pipeline_contracts import PipelineContext, PipelineStage
from ...core.projected_material import MaterialProjectionStats
IMPLEMENTATION_ID = 'projected-color-v1.2'
DEFAULT_ENABLE_VISIBILITY = True
DEFAULT_ALLOW_BACKFACE_FALLBACK = True
DEFAULT_FACING_POWER = 2.0
DEFAULT_MIN_FACING = 0.1
DEFAULT_RELATIVE_SCORE_CUTOFF = 0.2
DEFAULT_MAX_CONTRIBUTORS = 3
DEFAULT_WEIGHT_POWER = 1.5

@dataclass(frozen=True)
class ProjectedColorConfig:
    """
    Effective configuration of the built-in projected-color
    implementation.

    These defaults correspond to Material V1.2.

    They deliberately live at the implementation boundary,
    not in the generic pipeline core.
    """
    enable_visibility: bool = DEFAULT_ENABLE_VISIBILITY
    allow_backface_fallback: bool = DEFAULT_ALLOW_BACKFACE_FALLBACK
    facing_power: float = DEFAULT_FACING_POWER
    min_facing: float = DEFAULT_MIN_FACING
    relative_score_cutoff: float = DEFAULT_RELATIVE_SCORE_CUTOFF
    max_contributors: int = DEFAULT_MAX_CONTRIBUTORS
    weight_power: float = DEFAULT_WEIGHT_POWER

    def validate(self) -> None:
        if not math.isfinite(self.facing_power) or self.facing_power < 0.0:
            raise ValueError('Facing power must be finite and >= 0.')
        blend_config = self.to_blend_config()
        blend_config.validate()

    def to_blend_config(self) -> MaterialBlendConfig:
        return MaterialBlendConfig(min_facing=self.min_facing, facing_power=self.facing_power, relative_score_cutoff=self.relative_score_cutoff, max_contributors=self.max_contributors, weight_power=self.weight_power)

@dataclass(frozen=True)
class ProjectedColorOutput:
    """
    Output contract of projected-color-v1.2.

    The Blender object is the SAME surface object produced
    by the GEOMETRY stage.

        any GeometrySurfaceOutput
                 ↓
        Projected Color V1.2
                 ↓
        same Blender object
        + CORNER color attribute

    This output is intentionally geometry-implementation
    agnostic.

    geometry may therefore originate from:

        Native Visual Hull
        SDF Reconstruction
        imported surface
        future reconstruction engine
    """
    blender_object: bpy.types.Object
    geometry: GeometrySurfaceOutput
    stats: MaterialProjectionStats
    config: ProjectedColorConfig
    material_mode: str
    visibility_mode: str
    blend_mode: str
    color_attribute: str

    @property
    def projected_vertices(self) -> int:
        return self.stats.projected_vertices

    @property
    def fallback_vertices(self) -> int:
        return self.stats.fallback_vertices

    @property
    def selected_samples(self) -> int:
        return self.stats.selected_samples

    @property
    def visible_samples(self) -> int:
        return self.stats.visible_samples

    @property
    def occluded_samples(self) -> int:
        return self.stats.occluded_samples

def _resolve_settings(context: PipelineContext) -> Any:
    if context.settings is not None:
        return context.settings
    scene = context.scene
    if scene is None:
        return None
    return getattr(scene, 'bpt_settings', None)

def require_projected_color_output(context: PipelineContext) -> ProjectedColorOutput:
    """
    Typed accessor for EXPORT, diagnostics and future
    post-processing implementations.
    """
    output = context.require_output(PipelineStage.MATERIAL)
    if not isinstance(output, ProjectedColorOutput):
        raise TypeError(f'MATERIAL output is incompatible with "{IMPLEMENTATION_ID}". Expected ProjectedColorOutput, received {type(output).__name__}.')
    return output

def _read_setting(settings: Any, name: str, default: Any) -> Any:
    """
    Read an optional implementation-specific setting.

    The settings object may be:

        Blender BPT_PG_Settings
        SimpleNamespace from diagnostic scripts
        future implementation-specific settings adapter
    """
    if settings is None:
        return default
    return getattr(settings, name, default)

def _config_from_settings(settings: Any) -> ProjectedColorConfig:
    config = ProjectedColorConfig(enable_visibility=bool(_read_setting(settings, 'material_enable_visibility', DEFAULT_ENABLE_VISIBILITY)), allow_backface_fallback=bool(_read_setting(settings, 'material_allow_backface_fallback', DEFAULT_ALLOW_BACKFACE_FALLBACK)), facing_power=float(_read_setting(settings, 'material_facing_power', DEFAULT_FACING_POWER)), min_facing=float(_read_setting(settings, 'material_min_facing', DEFAULT_MIN_FACING)), relative_score_cutoff=float(_read_setting(settings, 'material_relative_score_cutoff', DEFAULT_RELATIVE_SCORE_CUTOFF)), max_contributors=int(_read_setting(settings, 'material_max_contributors', DEFAULT_MAX_CONTRIBUTORS)), weight_power=float(_read_setting(settings, 'material_weight_power', DEFAULT_WEIGHT_POWER)))
    config.validate()
    return config
