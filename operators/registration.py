from __future__ import annotations

import bpy

from .pipeline import (
    BPT_OT_GenerateCharacter,
    BPT_OT_RunPipeline,
    BPT_OT_RunPipelineStage,
)
from .presets import (
    BPT_OT_AddFrontSidePreset,
    BPT_OT_AddTurntablePreset,
    BPT_OT_UseGLBAutoPipeline,
    BPT_OT_UseGLBCanonicalPipeline,
    BPT_OT_UseGLBFirstPipeline,
)
from .projections import (
    BPT_OT_AddProjection,
    BPT_OT_ImportTurntableImages,
    BPT_OT_LoadProjectionImage,
    BPT_OT_RemoveProjection,
)
from .runtime import clear_pipeline_runtime_state
from .modular_export import BPT_OT_ExportExistingModularSource
from .rig_refinement import BPT_OT_RefineHeadWeights, BPT_OT_RefineOwnedSkin, BPT_OT_AlignAuthoredShoulders
from .modular_authoring import (
    BPT_OT_LoadModularFaceOwnership, BPT_OT_AssignModularFaces, BPT_OT_SaveModularFaceOwnership,
    BPT_OT_PrepareModularSource,
)
from .selection import (
    BPT_OT_ResetPipelineSettings,
    BPT_OT_SetPipelineImplementation,
    BPT_OT_SetPipelineStageEnabled,
)

CLASSES = (
    BPT_OT_LoadProjectionImage,

    BPT_OT_ImportTurntableImages,

    BPT_OT_AddProjection,

    BPT_OT_RemoveProjection,

    BPT_OT_AddTurntablePreset,

    BPT_OT_AddFrontSidePreset,

    BPT_OT_UseGLBAutoPipeline,
    BPT_OT_UseGLBFirstPipeline,
    BPT_OT_UseGLBCanonicalPipeline,

    BPT_OT_SetPipelineImplementation,
    BPT_OT_SetPipelineStageEnabled,


    BPT_OT_ResetPipelineSettings,

    BPT_OT_RunPipeline,

    BPT_OT_RunPipelineStage,

    BPT_OT_GenerateCharacter,
    BPT_OT_ExportExistingModularSource,
    BPT_OT_RefineHeadWeights,
    BPT_OT_RefineOwnedSkin,
    BPT_OT_AlignAuthoredShoulders,
    BPT_OT_LoadModularFaceOwnership,
    BPT_OT_AssignModularFaces,
    BPT_OT_SaveModularFaceOwnership,
    BPT_OT_PrepareModularSource,
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
