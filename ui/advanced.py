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

from .helpers import (
    STAGE_ICONS,
    STAGE_RUN_LABELS,
    _descriptor_for_selection,
    _draw_wrapped_text,
    _stage_status,
)

class AdvancedMixin:
    def _draw_advanced(
        self,
        layout,
        context: bpy.types.Context,
        settings,
    ) -> None:
        pipeline = (
            settings.pipeline
        )

        box = (
            layout.box()
        )

        header = (
            box.row(
                align=True
            )
        )

        header.prop(
            pipeline,
            "advanced_expanded",
            text="",
            emboss=False,
            icon=(
                "TRIA_DOWN"
                if (
                    pipeline
                    .advanced_expanded
                )
                else "TRIA_RIGHT"
            ),
        )

        header.label(
            text="Advanced",
            icon="PREFERENCES",
        )

        if not (
            pipeline
            .advanced_expanded
        ):
            return

        registry = (
            box.box()
        )

        registry.label(
            text="Pipeline Registry",
            icon="SETTINGS",
        )

        registry.label(
            text=(
                f"{len(PIPELINE_REGISTRY)} "
                "implementations registered"
            )
        )

        for stage in (
            PIPELINE_STAGE_ORDER
        ):
            stage_settings = (
                pipeline_stage_settings(
                    settings,
                    stage,
                )
            )

            row = (
                registry.row()
            )

            row.label(
                text=(
                    stage_spec(
                        stage
                    )
                    .label
                ),
                icon=(
                    STAGE_ICONS[
                        stage
                    ]
                ),
            )

            value = (
                row.row()
            )

            value.alignment = (
                "RIGHT"
            )

            implementation_id = (
                stage_settings
                .implementation_id
                .strip()
            )

            value.label(
                text=(
                    implementation_id
                    or "—"
                )
            )

        box.separator()

        reset = (
            box.row()
        )

        reset.operator(
            "bpt.reset_pipeline_settings",
            text="Reset Pipeline Configuration",
            icon="FILE_REFRESH",
        )


# ---------------------------------------------------------
# Classes
# ---------------------------------------------------------
