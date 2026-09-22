from __future__ import annotations

import math
import textwrap

import bpy
from bpy.types import Panel, UIList

from ..core.pipeline_contracts import PipelineStage, PIPELINE_STAGE_ORDER, stage_spec
from ..core.pipeline_registry import PIPELINE_REGISTRY
from ..operators import get_last_pipeline_context, get_last_pipeline_report
from ..properties import pipeline_stage_settings
from ..version import get_version_label



# ---------------------------------------------------------
# UI constants
# ---------------------------------------------------------

STAGE_ICONS: dict[
    PipelineStage,
    str,
] = {
    PipelineStage.INPUT:
        "CAMERA_DATA",

    PipelineStage.GEOMETRY:
        "MESH_DATA",

    PipelineStage.MATERIAL:
        "MATERIAL",

    PipelineStage.RIG:
        "ARMATURE_DATA",

    PipelineStage.EXPORT:
        "EXPORT",
}


STAGE_RUN_LABELS: dict[
    PipelineStage,
    str,
] = {
    PipelineStage.GEOMETRY:
        "Run Geometry",

    PipelineStage.MATERIAL:
        "Build Material",

    PipelineStage.RIG:
        "Generate Rig",

    PipelineStage.EXPORT:
        "Export",
}


# ---------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------

def _draw_wrapped_text(
    layout,
    text: str,
    *,
    width: int = 42,
    icon: str = "NONE",
) -> None:
    """
    Blender labels do not wrap automatically.
    """

    normalized = (
        str(
            text
        )
        .strip()
    )

    if not normalized:
        return

    lines = textwrap.wrap(
        normalized,
        width=width,
    )

    for index, line in enumerate(
        lines
    ):
        layout.label(
            text=line,
            icon=(
                icon
                if index == 0
                else "NONE"
            ),
        )


def _descriptor_for_selection(
    stage: PipelineStage,
    implementation_id: str,
):
    if not implementation_id:
        return None

    try:
        entry = (
            PIPELINE_REGISTRY
            .require_entry(
                implementation_id
            )
        )

    except Exception:
        return None

    if (
        entry.descriptor.stage
        != stage
    ):
        return None

    return (
        entry.descriptor
    )


def _stage_status(
    context: bpy.types.Context,
    stage: PipelineStage,
):
    """
    Return:

        text
        icon
        alert
    """

    settings = (
        context
        .scene
        .bpt_settings
    )

    stage_settings = (
        pipeline_stage_settings(
            settings,
            stage,
        )
    )

    descriptors = (
        PIPELINE_REGISTRY
        .descriptors(
            stage
        )
    )

    if not descriptors:
        return (
            "Not implemented",
            "INFO",
            False,
        )

    if not stage_settings.enabled:
        return (
            "Disabled",
            "INFO",
            False,
        )

    implementation_id = (
        stage_settings
        .implementation_id
        .strip()
    )

    if not implementation_id:
        return (
            "Not configured",
            "ERROR",
            True,
        )

    descriptor = (
        _descriptor_for_selection(
            stage,
            implementation_id,
        )
    )

    if descriptor is None:
        return (
            "Implementation missing",
            "ERROR",
            True,
        )

    report = (
        get_last_pipeline_report(
            context.scene
        )
    )

    if report is not None:
        record = (
            report.record_for(
                stage
            )
        )

        if record is not None:
            if record.success:
                return (
                    "Last run OK",
                    "CHECKMARK",
                    False,
                )

            if record.failed:
                return (
                    "Last run failed",
                    "ERROR",
                    True,
                )

            if record.skipped:
                return (
                    "Skipped",
                    "INFO",
                    False,
                )

    pipeline_context = (
        get_last_pipeline_context(
            context.scene
        )
    )

    if (
        pipeline_context is not None
        and pipeline_context.has_output(
            stage
        )
    ):
        return (
            "Output ready",
            "CHECKMARK",
            False,
        )

    return (
        "Configured",
        "INFO",
        False,
    )


# ---------------------------------------------------------
# Projection UI list
# ---------------------------------------------------------
