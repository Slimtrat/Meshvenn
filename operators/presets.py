from __future__ import annotations

import math
import os
import re

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator

from bpy_extras.io_utils import ImportHelper

from ..core.pipeline_contracts import (
    PipelineContext,
    PipelinePlan,
    PipelineStage,
    PIPELINE_STAGE_ORDER,
)
from ..core.pipeline_registry import PIPELINE_REGISTRY
from ..core.pipeline_runner import (
    PipelineExecutionReport,
    PipelineRunOptions,
    PipelineRunner,
)
from ..properties import (
    build_pipeline_plan,
    pipeline_stage_settings,
    reset_pipeline_defaults,
    set_pipeline_implementation,
)

from .runtime import clear_pipeline_runtime_state

class BPT_OT_AddTurntablePreset(
    Operator
):
    bl_idname = (
        "bpt.add_turntable_preset"
    )

    bl_label = (
        "Add Turntable Preset"
    )

    bl_description = (
        "Add evenly spaced horizontal "
        "projection slots"
    )

    view_count: IntProperty(
        name="Views",
        default=8,
        min=3,
        max=64,
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        settings.projections.clear()

        angle_step = (
            360.0
            / self.view_count
        )

        for index in range(
            self.view_count
        ):
            projection = (
                settings
                .projections
                .add()
            )

            angle_deg = (
                index
                * angle_step
            )

            projection.name = (
                f"{angle_deg:.1f}°"
            )

            projection.azimuth = (
                math.radians(
                    angle_deg
                )
            )

            projection.elevation = 0.0

            projection.enabled = True

            projection.flip_x = False

        settings.active_projection_index = 0

        clear_pipeline_runtime_state(
            context.scene
        )

        return {
            "FINISHED"
        }


class BPT_OT_AddFrontSidePreset(
    Operator
):
    bl_idname = (
        "bpt.add_front_side_preset"
    )

    bl_label = (
        "Front + Side"
    )

    bl_description = (
        "Create a simple front and side "
        "projection setup"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        settings.projections.clear()

        front = (
            settings
            .projections
            .add()
        )

        front.name = "Front"

        front.azimuth = (
            math.radians(
                0.0
            )
        )

        front.elevation = 0.0

        front.enabled = True

        front.flip_x = False

        side = (
            settings
            .projections
            .add()
        )

        side.name = "Right"

        side.azimuth = (
            math.radians(
                90.0
            )
        )

        side.elevation = 0.0

        side.enabled = True

        side.flip_x = False

        settings.active_projection_index = 0

        clear_pipeline_runtime_state(
            context.scene
        )

        return {
            "FINISHED"
        }


def _apply_glb_pipeline(context: bpy.types.Context, *, route: str) -> None:
    route_implementations = {
        "auto": (
            "glb-auto-geometry-v1",
            "glb-auto-rig-v1",
            "glb-auto-motion-v1",
        ),
        "preserve": (
            "glb-preserved-geometry-v1",
            "glb-source-rig-v1",
            "glb-source-motion-v1",
        ),
        "canonicalize": (
            "glb-normalized-geometry-v1",
            "canonical-biped-v1",
            "canonical-motion-retarget-v1",
        ),
    }
    try:
        geometry_id, rig_id, motion_id = route_implementations[route]
    except KeyError as exc:
        raise ValueError(f"Unknown GLB pipeline route: {route}") from exc
    settings = context.scene.bpt_settings
    selections = {
        PipelineStage.INPUT: ("glb-file-v1", True, True),
        PipelineStage.GEOMETRY: (geometry_id, True, True),
        PipelineStage.MATERIAL: ("projected-color-v1.2", False, False),
        PipelineStage.RIG: (rig_id, True, True),
        PipelineStage.MOTION: (motion_id, True, True),
        PipelineStage.EXPORT: ("glb-export-v1", True, True),
    }
    for stage, (implementation_id, enabled, expanded) in selections.items():
        stage_settings = pipeline_stage_settings(settings, stage)
        stage_settings.implementation_id = implementation_id
        stage_settings.enabled = enabled
        stage_settings.expanded = expanded
    clear_pipeline_runtime_state(context.scene)


class BPT_OT_UseGLBFirstPipeline(Operator):
    bl_idname = "bpt.use_glb_first_pipeline"
    bl_label = "Use GLB Source-Preservation Pipeline"
    bl_description = (
        "Keep the GLB source meshes, rig, skin and Motion through validated export"
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        _apply_glb_pipeline(context, route="preserve")
        return {"FINISHED"}


class BPT_OT_UseGLBAutoPipeline(Operator):
    bl_idname = "bpt.use_glb_auto_pipeline"
    bl_label = "Use GLB Automatic Pipeline"
    bl_description = (
        "Select Canonical, source-preservation or geometry-only routing from the GLB rig"
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        _apply_glb_pipeline(context, route="auto")
        return {"FINISHED"}


class BPT_OT_UseGLBCanonicalPipeline(Operator):
    bl_idname = "bpt.use_glb_canonical_pipeline"
    bl_label = "Use GLB Canonicalization Pipeline"
    bl_description = (
        "Normalize GLB geometry, rebuild a Canonical Biped and retarget Motion"
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        _apply_glb_pipeline(context, route="canonicalize")
        return {"FINISHED"}


# ---------------------------------------------------------
# Generic pipeline implementation selection
# ---------------------------------------------------------
