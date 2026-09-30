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
    stage_spec,
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

from .constants import PIPELINE_STAGE_ENUM_ITEMS
from .runtime import clear_pipeline_runtime_state


def _enable_stage_with_dependencies(
    settings,
    stage: PipelineStage,
) -> None:
    pending = [stage]
    enabled_stages: set[PipelineStage] = set()
    while pending:
        current = pending.pop()
        if current in enabled_stages:
            continue
        current_settings = pipeline_stage_settings(settings, current)
        if not current_settings.implementation_id.strip():
            default_id = PIPELINE_REGISTRY.default_id(current)
            if default_id is None:
                raise ValueError(
                    f'Pipeline dependency "{current.value}" '
                    "has no default implementation."
                )
            set_pipeline_implementation(settings, current, default_id)
        current_settings.enabled = True
        enabled_stages.add(current)
        pending.extend(
            dependency
            for dependency in stage_spec(current).required_stages
            if dependency not in enabled_stages
        )


def _disable_stage_with_dependents(
    settings,
    stage: PipelineStage,
) -> None:
    pending = [stage]
    disabled_stages: set[PipelineStage] = set()
    while pending:
        current = pending.pop()
        if current in disabled_stages:
            continue
        pipeline_stage_settings(settings, current).enabled = False
        disabled_stages.add(current)
        pending.extend(
            candidate
            for candidate in PIPELINE_STAGE_ORDER
            if current in stage_spec(candidate).required_stages
            and candidate not in disabled_stages
        )


class BPT_OT_SetPipelineStageEnabled(Operator):
    """Dependency-aware pipeline stage toggle used by the visible stage cards."""

    bl_idname = "bpt.set_pipeline_stage_enabled"
    bl_label = "Set Pipeline Stage Enabled"
    bl_description = "Enable this stage and its dependencies, or disable its dependents"

    stage: EnumProperty(
        name="Stage",
        items=PIPELINE_STAGE_ENUM_ITEMS,
        default=PipelineStage.GEOMETRY.value,
    )
    enabled: BoolProperty(
        name="Enabled",
        default=True,
        options={"HIDDEN"},
    )

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            stage = PipelineStage(self.stage)
            settings = context.scene.bpt_settings
            if self.enabled:
                _enable_stage_with_dependencies(settings, stage)
            else:
                _disable_stage_with_dependents(settings, stage)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not update pipeline stage: {exc}")
            return {"CANCELLED"}

        clear_pipeline_runtime_state(context.scene)
        return {"FINISHED"}


class BPT_OT_SetPipelineImplementation(
    Operator
):
    """
    Generic implementation-selection action.

    ui.py can create one of these buttons for every
    ImplementationDescriptor exposed by PIPELINE_REGISTRY.

    No algorithm-specific operator is required.
    """

    bl_idname = (
        "bpt.set_pipeline_implementation"
    )

    bl_label = (
        "Select Implementation"
    )

    bl_description = (
        "Select the implementation used "
        "for a pipeline stage"
    )

    stage: EnumProperty(
        name="Stage",
        items=(
            PIPELINE_STAGE_ENUM_ITEMS
        ),
        default=(
            PipelineStage.GEOMETRY.value
        ),
    )

    implementation_id: StringProperty(
        name="Implementation",
        default="",
    )

    enable_stage: BoolProperty(
        name="Enable Stage",
        default=True,
        options={
            "HIDDEN",
        },
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

            implementation_id = (
                self
                .implementation_id
                .strip()
            )

            if not implementation_id:
                raise ValueError(
                    (
                        "Implementation id "
                        "cannot be empty."
                    )
                )

            implementation = (
                PIPELINE_REGISTRY
                .require(
                    implementation_id,
                    stage=stage,
                )
            )

            set_pipeline_implementation(
                settings,
                stage,
                implementation
                .descriptor
                .identifier,
            )

            if self.enable_stage:
                _enable_stage_with_dependencies(settings, stage)

        except Exception as exc:
            self.report(
                {"ERROR"},
                (
                    "Could not select "
                    f"implementation: {exc}"
                ),
            )

            return {
                "CANCELLED"
            }

        clear_pipeline_runtime_state(
            context.scene
        )

        self.report(
            {"INFO"},
            (
                f"{stage.value.title()}: "
                f"{implementation.descriptor.label}"
            ),
        )

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Pipeline reset
# ---------------------------------------------------------

class BPT_OT_ResetPipelineSettings(
    Operator
):
    bl_idname = (
        "bpt.reset_pipeline_settings"
    )

    bl_label = (
        "Reset Pipeline"
    )

    bl_description = (
        "Reset pipeline stage selections "
        "without deleting projection images "
        "or generation parameters"
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

        reset_pipeline_defaults(
            settings
        )

        clear_pipeline_runtime_state(
            context.scene
        )

        self.report(
            {"INFO"},
            "Pipeline settings reset.",
        )

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Complete pipeline
# ---------------------------------------------------------
