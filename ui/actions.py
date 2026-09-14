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

class StageActionsMixin:
    def _draw_stage_action(
        self,
        layout,
        stage: PipelineStage,
        stage_settings,
        descriptors,
    ) -> None:
        if not descriptors:
            return

        implementation_id = (
            stage_settings
            .implementation_id
            .strip()
        )

        if not implementation_id:
            return

        row = (
            layout.row()
        )

        row.enabled = (
            stage_settings.enabled
            and (
                _descriptor_for_selection(
                    stage,
                    implementation_id,
                )
                is not None
            )
        )

        row.scale_y = 1.15

        operator = (
            row.operator(
                "bpt.run_pipeline_stage",
                text=(
                    STAGE_RUN_LABELS
                    .get(
                        stage,
                        "Run Stage",
                    )
                ),
                icon="PLAY",
            )
        )

        operator.stage = (
            stage.value
        )

    # -----------------------------------------------------
    # Generate all
    # -----------------------------------------------------

    def _draw_generate_all(
        self,
        layout,
        settings,
    ) -> None:
        box = (
            layout.box()
        )

        row = (
            box.row()
        )

        row.scale_y = 1.8

        row.operator(
            "bpt.run_pipeline",
            text="GENERATE ALL",
            icon="PLAY",
        )

        enabled_labels = []

        for stage in (
            PIPELINE_STAGE_ORDER
        ):
            current = (
                pipeline_stage_settings(
                    settings,
                    stage,
                )
            )

            if (
                current.enabled
                and current
                .implementation_id
                .strip()
            ):
                enabled_labels.append(
                    stage_spec(
                        stage
                    )
                    .label
                )

        if enabled_labels:
            box.label(
                text=(
                    " → ".join(
                        enabled_labels
                    )
                ),
                icon="INFO",
            )

    # -----------------------------------------------------
    # Last pipeline run
    # -----------------------------------------------------
