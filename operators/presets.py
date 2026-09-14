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


# ---------------------------------------------------------
# Generic pipeline implementation selection
# ---------------------------------------------------------
