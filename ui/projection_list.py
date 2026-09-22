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

class BPT_UL_ProjectionViews(
    UIList
):
    def draw_item(
        self,
        context: bpy.types.Context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_property,
        index: int,
    ) -> None:
        projection = item

        row = layout.row(
            align=True
        )

        row.prop(
            projection,
            "enabled",
            text="",
        )

        row.prop(
            projection,
            "name",
            text="",
            emboss=False,
            icon="CAMERA_DATA",
        )

        angle_row = row.row()

        angle_row.alignment = (
            "RIGHT"
        )

        angle_row.label(
            text=(
                f"{math.degrees(projection.azimuth):.0f}°"
            )
        )

        angle_row.label(
            text="",
            icon=(
                "CHECKMARK"
                if projection.image
                is not None
                else "ERROR"
            ),
        )


# ---------------------------------------------------------
# Main panel
# ---------------------------------------------------------
