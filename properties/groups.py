"""Compatibility facade for Blender property groups."""

from .base_groups import (
    BPT_PG_PipelineSettings,
    BPT_PG_PipelineStageSettings,
    BPT_PG_ProjectionView,
)
from .settings import BPT_PG_Settings
from .stage_mapping import PIPELINE_STAGE_DEFAULTS, PIPELINE_STAGE_PROPERTY_NAMES

__all__ = (
    "BPT_PG_PipelineSettings",
    "BPT_PG_PipelineStageSettings",
    "BPT_PG_ProjectionView",
    "BPT_PG_Settings",
    "PIPELINE_STAGE_DEFAULTS",
    "PIPELINE_STAGE_PROPERTY_NAMES",
)
