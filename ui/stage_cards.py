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

class StageCardsMixin:
    def draw(
        self,
        context: bpy.types.Context,
    ) -> None:
        layout = (
            self.layout
        )

        scene = (
            context.scene
        )

        settings = getattr(
            scene,
            "bpt_settings",
            None,
        )

        if settings is None:
            box = layout.box()

            box.alert = True

            box.label(
                text=(
                    "Meshvenn settings unavailable"
                ),
                icon="ERROR",
            )

            return

        self._draw_header(
            layout
        )

        layout.separator()

        for stage in (
            PIPELINE_STAGE_ORDER
        ):
            self._draw_stage(
                layout,
                context,
                settings,
                stage,
            )

        layout.separator()

        self._draw_generate_all(
            layout,
            settings,
        )

        layout.separator()

        self._draw_last_run(
            layout,
            context,
            settings,
        )

        self._draw_advanced(
            layout,
            context,
            settings,
        )

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

    def _draw_header(
        self,
        layout,
    ) -> None:
        row = layout.row(
            align=True
        )

        row.label(
            text="Meshvenn",
            icon="MESH_ICOSPHERE",
        )

        version = row.row()

        version.alignment = (
            "RIGHT"
        )

        version.label(
            text=get_version_label(),
        )

        description = (
            layout.row()
        )

        description.label(
            text=(
                "Images → Geometry → Material → Rig → Export"
            )
        )

    # -----------------------------------------------------
    # Generic stage card
    # -----------------------------------------------------

    def _draw_stage(
        self,
        layout,
        context: bpy.types.Context,
        settings,
        stage: PipelineStage,
    ) -> None:
        spec = (
            stage_spec(
                stage
            )
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

        (
            status_text,
            status_icon,
            status_alert,
        ) = _stage_status(
            context,
            stage,
        )

        box = layout.box()

        # -------------------------------------------------
        # Header
        # -------------------------------------------------

        header = box.row(
            align=True
        )

        header.prop(
            stage_settings,
            "expanded",
            text="",
            emboss=False,
            icon=(
                "TRIA_DOWN"
                if stage_settings.expanded
                else "TRIA_RIGHT"
            ),
        )

        enabled_column = (
            header.row(
                align=True
            )
        )

        enabled_column.enabled = bool(
            descriptors
        )

        enabled_column.prop(
            stage_settings,
            "enabled",
            text="",
        )

        header.label(
            text=(
                spec.label.upper()
            ),
            icon=(
                STAGE_ICONS[
                    stage
                ]
            ),
        )

        status = (
            header.row()
        )

        status.alignment = (
            "RIGHT"
        )

        status.alert = (
            status_alert
        )

        status.label(
            text=status_text,
            icon=status_icon,
        )

        if not stage_settings.expanded:
            return

        # -------------------------------------------------
        # Stage body
        # -------------------------------------------------

        body = box.column()

        self._draw_implementation_selector(
            body,
            context,
            settings,
            stage,
            descriptors,
        )

        implementation_id = (
            stage_settings
            .implementation_id
            .strip()
        )

        if (
            implementation_id
            and descriptors
        ):
            body.separator()

            config = body.column()

            config.enabled = (
                stage_settings.enabled
            )

            self._draw_implementation_settings(
                config,
                context,
                settings,
                stage,
                implementation_id,
            )

        # -------------------------------------------------
        # Per-stage action
        # -------------------------------------------------

        if (
            stage
            != PipelineStage.INPUT
        ):
            self._draw_stage_action(
                body,
                stage,
                stage_settings,
                descriptors,
            )

    # -----------------------------------------------------
    # Implementation selector
    # -----------------------------------------------------
