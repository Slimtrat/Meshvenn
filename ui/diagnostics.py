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

class DiagnosticsMixin:
    def _draw_last_run(
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
            "diagnostics_expanded",
            text="",
            emboss=False,
            icon=(
                "TRIA_DOWN"
                if (
                    pipeline
                    .diagnostics_expanded
                )
                else "TRIA_RIGHT"
            ),
        )

        header.label(
            text="Last Run",
            icon="INFO",
        )

        report = (
            get_last_pipeline_report(
                context.scene
            )
        )

        if report is None:
            status = (
                header.row()
            )

            status.alignment = (
                "RIGHT"
            )

            status.label(
                text="None",
            )

            if (
                pipeline
                .diagnostics_expanded
            ):
                box.label(
                    text=(
                        "No pipeline execution yet."
                    ),
                    icon="INFO",
                )

            return

        status = (
            header.row()
        )

        status.alignment = (
            "RIGHT"
        )

        status.alert = (
            not report.success
        )

        status.label(
            text=(
                "Success"
                if report.success
                else "Failed"
            ),
            icon=(
                "CHECKMARK"
                if report.success
                else "ERROR"
            ),
        )

        if not (
            pipeline
            .diagnostics_expanded
        ):
            return

        summary = (
            box.row()
        )

        summary.label(
            text=(
                f"{report.duration_seconds:.3f}s"
            ),
            icon="TIME",
        )

        for record in (
            report.records
        ):
            stage_box = (
                box.box()
            )

            row = (
                stage_box.row()
            )

            row.label(
                text=(
                    stage_spec(
                        record.stage
                    )
                    .label
                ),
                icon=(
                    STAGE_ICONS[
                        record.stage
                    ]
                ),
            )

            state = (
                row.row()
            )

            state.alignment = (
                "RIGHT"
            )

            state.alert = (
                record.failed
            )

            state.label(
                text=(
                    record
                    .result
                    .state
                    .value
                    .title()
                ),
                icon=(
                    "CHECKMARK"
                    if record.success
                    else (
                        "ERROR"
                        if record.failed
                        else "INFO"
                    )
                ),
            )

            if (
                record.result.message
            ):
                _draw_wrapped_text(
                    stage_box,
                    record
                    .result
                    .message,
                    width=38,
                )

            stage_box.label(
                text=(
                    f"{record.duration_seconds:.3f}s"
                ),
                icon="TIME",
            )

    # -----------------------------------------------------
    # Advanced
    # -----------------------------------------------------
