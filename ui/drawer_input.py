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
class ProjectionInputDrawerMixin:
    def _draw_projection_input(
        self,
        layout,
        settings,
    ) -> None:
        active_views = 0

        ready_views = 0

        missing_views = 0

        for projection in (
            settings.projections
        ):
            if not projection.enabled:
                continue

            active_views += 1

            if projection.image is None:
                missing_views += 1

            else:
                ready_views += 1

        # -------------------------------------------------
        # Input status
        # -------------------------------------------------

        status = (
            layout.row(
                align=True
            )
        )

        status.label(
            text=(
                f"{ready_views}/{active_views} "
                "enabled views ready"
            ),
            icon=(
                "CHECKMARK"
                if ready_views >= 2
                else "ERROR"
            ),
        )

        # -------------------------------------------------
        # Projection list
        # -------------------------------------------------

        row = layout.row()

        row.template_list(
            "BPT_UL_ProjectionViews",
            "",
            settings,
            "projections",
            settings,
            "active_projection_index",
            rows=5,
        )

        controls = (
            row.column(
                align=True
            )
        )

        controls.operator(
            "bpt.add_projection",
            text="",
            icon="ADD",
        )

        if len(
            settings.projections
        ) > 0:
            remove = (
                controls.operator(
                    "bpt.remove_projection",
                    text="",
                    icon="REMOVE",
                )
            )

            remove.index = (
                settings
                .active_projection_index
            )

        # -------------------------------------------------
        # Import / presets
        # -------------------------------------------------

        tools = (
            layout.box()
        )

        tools.label(
            text="Add Views",
            icon="CAMERA_DATA",
        )

        import_row = (
            tools.row()
        )

        import_row.operator(
            (
                "bpt."
                "import_turntable_images"
            ),
            text="Import Images",
            icon="FILE_FOLDER",
        )

        preset = (
            tools.row(
                align=True
            )
        )

        preset.operator(
            (
                "bpt."
                "add_front_side_preset"
            ),
            text="Front + Side",
        )

        for count in (
            4,
            8,
            16,
        ):
            operator = (
                preset.operator(
                    (
                        "bpt."
                        "add_turntable_preset"
                    ),
                    text=str(
                        count
                    ),
                )
            )

            operator.view_count = (
                count
            )

        # -------------------------------------------------
        # Selected projection
        # -------------------------------------------------

        if settings.projections:
            index = min(
                settings
                .active_projection_index,
                len(
                    settings.projections
                )
                - 1,
            )

            projection = (
                settings.projections[
                    index
                ]
            )

            detail = (
                layout.box()
            )

            detail.label(
                text="Selected View",
                icon="IMAGE_DATA",
            )

            detail.prop(
                projection,
                "enabled",
            )

            detail.prop(
                projection,
                "name",
            )

            detail.prop(
                projection,
                "image",
            )

            load = (
                detail.operator(
                    (
                        "bpt."
                        "load_projection_image"
                    ),
                    text="Load Image",
                    icon="FILE_IMAGE",
                )
            )

            load.index = (
                index
            )

            detail.prop(
                projection,
                "azimuth",
            )

            detail.prop(
                projection,
                "elevation",
            )

            detail.prop(
                projection,
                "flip_x",
            )

            detail.prop(
                projection,
                "weight",
                slider=True,
            )

        # -------------------------------------------------
        # Input extraction
        # -------------------------------------------------

        extraction = (
            layout.box()
        )

        extraction.label(
            text="Silhouette",
            icon="MOD_MASK",
        )

        extraction.prop(
            settings,
            "alpha_threshold",
            text="Alpha Threshold",
            slider=True,
        )

        if ready_views < 2:
            warning = (
                extraction.row()
            )

            warning.alert = True

            warning.label(
                text=(
                    "At least 2 images required"
                ),
                icon="ERROR",
            )

        elif missing_views > 0:
            warning = (
                extraction.row()
            )

            warning.label(
                text=(
                    f"{missing_views} enabled view"
                    + (
                        "s"
                        if missing_views != 1
                        else ""
                    )
                    + " without image"
                ),
                icon="INFO",
            )

    # -----------------------------------------------------
    # GEOMETRY
    # -----------------------------------------------------
