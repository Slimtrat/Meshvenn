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

from .constants import PIPELINE_STAGE_ENUM_ITEMS, RUNNABLE_STAGE_ENUM_ITEMS
from .runtime_state import _store_pipeline_runtime

# ---------------------------------------------------------
# Pipeline report helpers
# ---------------------------------------------------------

def _pipeline_failure_message(
    report: PipelineExecutionReport,
) -> str:
    message = (
        report
        .failure_message
        .strip()
    )

    if not message:
        return (
            "Pipeline execution failed."
        )

    # Blender status reports are easier to read when kept
    # to one line. Complete details remain in the runtime
    # PipelineExecutionReport.
    first_line = (
        message
        .splitlines()[0]
        .strip()
    )

    return (
        first_line
        or "Pipeline execution failed."
    )


def _pipeline_success_message(
    report: PipelineExecutionReport,
) -> str:
    successful = (
        report
        .successful_records
    )

    if successful:
        message = (
            successful[-1]
            .result
            .message
            .strip()
        )

        if message:
            return message

    stage_count = len(
        successful
    )

    return (
        "Meshvenn pipeline completed "
        f"with {stage_count} successful stage"
        + (
            "s."
            if stage_count != 1
            else "."
        )
    )
def _new_pipeline_context(
    context: bpy.types.Context,
) -> PipelineContext:
    scene = (
        context.scene
    )

    if scene is None:
        raise RuntimeError(
            "No active Blender scene."
        )

    settings = getattr(
        scene,
        "bpt_settings",
        None,
    )

    if settings is None:
        raise RuntimeError(
            "Meshvenn settings are unavailable."
        )

    return (
        PipelineContext(
            scene=scene,
            settings=settings,
            metadata={
                "source": "blender-ui",
            },
        )
    )


def _execute_pipeline_plan(
    operator: Operator,
    context: bpy.types.Context,
    plan: PipelinePlan,
) -> set[str]:
    """
    Common Blender -> PipelineRunner boundary.

    All generation operators must pass through here instead
    of invoking concrete implementations themselves.
    """

    scene = (
        context.scene
    )

    if scene is None:
        operator.report(
            {"ERROR"},
            "No active Blender scene.",
        )

        return {
            "CANCELLED"
        }

    try:
        pipeline_context = (
            _new_pipeline_context(
                context
            )
        )

        runner = (
            PipelineRunner(
                PIPELINE_REGISTRY
            )
        )

        report = (
            runner.run(
                plan,
                pipeline_context,
                options=(
                    PipelineRunOptions(
                        stop_on_failure=True,
                        catch_exceptions=True,
                        check_availability=True,
                    )
                ),
            )
        )

    except Exception as exc:
        operator.report(
            {"ERROR"},
            (
                "Pipeline could not start: "
                f"{exc}"
            ),
        )

        return {
            "CANCELLED"
        }

    _store_pipeline_runtime(
        scene,
        pipeline_context,
        report,
    )

    if not report.success:
        operator.report(
            {"ERROR"},
            _pipeline_failure_message(
                report
            ),
        )

        return {
            "CANCELLED"
        }

    operator.report(
        {"INFO"},
        _pipeline_success_message(
            report
        ),
    )

    return {
        "FINISHED"
    }


# ---------------------------------------------------------
# Pipeline plan helpers
# ---------------------------------------------------------

def _plan_through_stage(
    settings,
    target_stage: PipelineStage,
) -> PipelinePlan:
    """
    Build a deterministic pipeline prefix.

    Example:

        target = GEOMETRY

            INPUT
            GEOMETRY

        target = MATERIAL

            INPUT
            GEOMETRY
            MATERIAL

        target = RIG

            INPUT
            GEOMETRY
            MATERIAL if configured
            RIG

    Disabled stages remain disabled in the plan. This keeps
    the user's persistent pipeline configuration authoritative.
    """

    full_plan = (
        build_pipeline_plan(
            settings
        )
    )

    target_selection = (
        full_plan
        .selection_for(
            target_stage
        )
    )

    if target_selection is None:
        raise ValueError(
            (
                f'Pipeline stage "{target_stage.value}" '
                "has no implementation selected."
            )
        )

    if not target_selection.enabled:
        raise ValueError(
            (
                f'Pipeline stage "{target_stage.value}" '
                "is disabled."
            )
        )

    target_index = (
        PIPELINE_STAGE_ORDER
        .index(
            target_stage
        )
    )

    selections = tuple(
        selection
        for selection
        in full_plan.selections
        if (
            PIPELINE_STAGE_ORDER
            .index(
                selection.stage
            )
            <= target_index
        )
    )

    return (
        PipelinePlan(
            selections=(
                selections
            )
        )
    )
