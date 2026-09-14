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

from .constants import ANGLE_PATTERN, IMAGE_FILTER
from .runtime import clear_pipeline_runtime_state
class BPT_OT_LoadProjectionImage(
    Operator,
    ImportHelper,
):
    bl_idname = (
        "bpt.load_projection_image"
    )

    bl_label = (
        "Load Projection Image"
    )

    bl_description = (
        "Load an image from disk and assign it "
        "to the selected projection"
    )

    filename_ext = ".png"

    filter_glob: StringProperty(
        default=IMAGE_FILTER,
        options={
            "HIDDEN",
        },
    )

    index: IntProperty(
        name="Projection Index",
        default=0,
        min=0,
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

        if (
            self.index < 0
            or self.index
            >= len(
                settings.projections
            )
        ):
            self.report(
                {"ERROR"},
                "Invalid projection index.",
            )

            return {
                "CANCELLED"
            }

        try:
            image = (
                bpy.data
                .images
                .load(
                    self.filepath,
                    check_existing=True,
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Could not load image: "
                    f"{exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        settings.projections[
            self.index
        ].image = (
            image
        )

        settings.active_projection_index = (
            self.index
        )

        # Prepared INPUT data from a previous run is now
        # potentially stale.
        clear_pipeline_runtime_state(
            context.scene
        )

        self.report(
            {"INFO"},
            (
                f'Loaded image "{image.name}".'
            ),
        )

        return {
            "FINISHED"
        }
