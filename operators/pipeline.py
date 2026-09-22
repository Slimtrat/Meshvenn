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

from .constants import RUNNABLE_STAGE_ENUM_ITEMS
from .runtime import _execute_pipeline_plan, _plan_through_stage

class BPT_OT_RunPipeline(
    Operator
):
    """
    Main Meshvenn product action.

    Blender
        ↓
    PipelinePlan
        ↓
    PipelineRunner
        ↓
    PIPELINE_REGISTRY
        ↓
    concrete implementations
    """

    bl_idname = (
        "bpt.run_pipeline"
    )

    bl_label = (
        "Generate"
    )

    bl_description = (
        "Run the configured Meshvenn pipeline"
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

        try:
            plan = (
                build_pipeline_plan(
                    settings
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Invalid pipeline "
                    f"configuration: {exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        return (
            _execute_pipeline_plan(
                self,
                context,
                plan,
            )
        )


# ---------------------------------------------------------
# Run pipeline through one stage
# ---------------------------------------------------------

class BPT_OT_RunPipelineStage(
    Operator
):
    """
    Run the pipeline up to a selected stage.

    This deliberately rebuilds required upstream stages.

    Example:

        Run Geometry

            INPUT
              ↓
            GEOMETRY

        Run Material

            INPUT
              ↓
            GEOMETRY
              ↓
            MATERIAL

    This makes stage execution deterministic for the first
    general UI version.

    Incremental reuse of previous stage outputs can be added
    later without changing the UI contract.
    """

    bl_idname = (
        "bpt.run_pipeline_stage"
    )

    bl_label = (
        "Run Stage"
    )

    bl_description = (
        "Run the configured pipeline "
        "through this stage"
    )

    stage: EnumProperty(
        name="Stage",
        items=(
            RUNNABLE_STAGE_ENUM_ITEMS
        ),
        default=(
            PipelineStage.GEOMETRY.value
        ),
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

        try:
            stage = (
                PipelineStage(
                    self.stage
                )
            )

            plan = (
                _plan_through_stage(
                    settings,
                    stage,
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Could not run "
                    f"{self.stage}: {exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        return (
            _execute_pipeline_plan(
                self,
                context,
                plan,
            )
        )


# ---------------------------------------------------------
# Legacy compatibility
# ---------------------------------------------------------

class BPT_OT_GenerateCharacter(
    Operator
):
    """
    Compatibility alias.

    Existing UI/scripts may still invoke:

        bpy.ops.bpt.generate_character()

    It now executes the exact same generic pipeline as:

        bpy.ops.bpt.run_pipeline()

    No reconstruction implementation exists in this
    operator anymore.
    """

    bl_idname = (
        "bpt.generate_character"
    )

    bl_label = (
        "Generate Scan"
    )

    bl_description = (
        "Compatibility alias for the "
        "Meshvenn generation pipeline"
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

        try:
            plan = (
                build_pipeline_plan(
                    settings
                )
            )

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Invalid pipeline "
                    f"configuration: {exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        return (
            _execute_pipeline_plan(
                self,
                context,
                plan,
            )
        )


# ---------------------------------------------------------
# Filename angle detection
# ---------------------------------------------------------
