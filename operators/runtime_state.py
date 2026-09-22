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
# ---------------------------------------------------------
# Runtime state
#
# Blender PropertyGroups store persistent configuration.
#
# Execution reports are runtime objects and should not be
# serialized into the .blend file wholesale.
#
# A lightweight summary is mirrored into Scene custom
# properties for diagnostics.
# ---------------------------------------------------------

_LAST_PIPELINE_REPORTS: dict[
    int,
    PipelineExecutionReport,
] = {}


_LAST_PIPELINE_CONTEXTS: dict[
    int,
    PipelineContext,
] = {}


def _scene_key(
    scene: bpy.types.Scene,
) -> int:
    return int(
        scene.as_pointer()
    )


def get_last_pipeline_report(
    scene: bpy.types.Scene,
) -> (
    PipelineExecutionReport
    | None
):
    """
    Runtime accessor intended for ui.py.
    """

    return (
        _LAST_PIPELINE_REPORTS
        .get(
            _scene_key(
                scene
            )
        )
    )


def get_last_pipeline_context(
    scene: bpy.types.Scene,
) -> (
    PipelineContext
    | None
):
    return (
        _LAST_PIPELINE_CONTEXTS
        .get(
            _scene_key(
                scene
            )
        )
    )


def clear_pipeline_runtime_state(
    scene: (
        bpy.types.Scene
        | None
    ) = None,
) -> None:
    if scene is None:
        _LAST_PIPELINE_REPORTS.clear()
        _LAST_PIPELINE_CONTEXTS.clear()

        return

    key = (
        _scene_key(
            scene
        )
    )

    _LAST_PIPELINE_REPORTS.pop(
        key,
        None,
    )

    _LAST_PIPELINE_CONTEXTS.pop(
        key,
        None,
    )
def _store_pipeline_runtime(
    scene: bpy.types.Scene,
    pipeline_context: PipelineContext,
    report: PipelineExecutionReport,
) -> None:
    key = (
        _scene_key(
            scene
        )
    )

    _LAST_PIPELINE_CONTEXTS[
        key
    ] = (
        pipeline_context
    )

    _LAST_PIPELINE_REPORTS[
        key
    ] = (
        report
    )

    # -----------------------------------------------------
    # Lightweight persistent diagnostic snapshot.
    # -----------------------------------------------------

    scene[
        "meshvenn_last_pipeline_status"
    ] = (
        "success"
        if report.success
        else "failed"
    )

    scene[
        "meshvenn_last_pipeline_duration"
    ] = float(
        report.duration_seconds
    )

    scene[
        "meshvenn_last_pipeline_aborted"
    ] = bool(
        report.aborted
    )

    scene[
        "meshvenn_last_pipeline_stage_count"
    ] = len(
        report.records
    )

    scene[
        "meshvenn_last_pipeline_successful_stages"
    ] = len(
        report.successful_records
    )

    scene[
        "meshvenn_last_pipeline_failed_stages"
    ] = len(
        report.failed_records
    )

    if report.success:
        scene[
            "meshvenn_last_pipeline_message"
        ] = (
            _pipeline_success_message(
                report
            )
        )

    else:
        scene[
            "meshvenn_last_pipeline_message"
        ] = (
            _pipeline_failure_message(
                report
            )
        )

    if report.records:
        scene[
            "meshvenn_last_pipeline_last_stage"
        ] = (
            report
            .records[-1]
            .stage
            .value
        )

    else:
        scene[
            "meshvenn_last_pipeline_last_stage"
        ] = ""
