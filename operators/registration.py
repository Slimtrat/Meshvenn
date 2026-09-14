from __future__ import annotations

import bpy

from .pipeline import (
    BPT_OT_GenerateCharacter,
    BPT_OT_RunPipeline,
    BPT_OT_RunPipelineStage,
)
from .presets import BPT_OT_AddFrontSidePreset, BPT_OT_AddTurntablePreset
from .projections import (
    BPT_OT_AddProjection,
    BPT_OT_ImportTurntableImages,
    BPT_OT_LoadProjectionImage,
    BPT_OT_RemoveProjection,
)
from .runtime import clear_pipeline_runtime_state
from .selection import BPT_OT_ResetPipelineSettings, BPT_OT_SetPipelineImplementation

CLASSES = (
    BPT_OT_LoadProjectionImage,

    BPT_OT_ImportTurntableImages,

    BPT_OT_AddProjection,

    BPT_OT_RemoveProjection,

    BPT_OT_AddTurntablePreset,

    BPT_OT_AddFrontSidePreset,

    BPT_OT_SetPipelineImplementation,

    BPT_OT_ResetPipelineSettings,

    BPT_OT_RunPipeline,

    BPT_OT_RunPipelineStage,

    BPT_OT_GenerateCharacter,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(
            cls
        )


def unregister() -> None:
    clear_pipeline_runtime_state()

    for cls in reversed(
        CLASSES
    ):
        bpy.utils.unregister_class(
            cls
        )
