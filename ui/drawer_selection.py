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
class ImplementationSelectionMixin:
    def _draw_implementation_selector(
        self,
        layout,
        context,
        settings,
        stage: PipelineStage,
        descriptors,
    ) -> None:
        stage_settings = (
            pipeline_stage_settings(
                settings,
                stage,
            )
        )

        current_id = (
            stage_settings
            .implementation_id
            .strip()
        )

        if not descriptors:
            info = layout.box()

            info.label(
                text=(
                    "No implementation registered yet"
                ),
                icon="INFO",
            )

            _draw_wrapped_text(
                info,
                (
                    "The pipeline stage already exists. "
                    "Adding an implementation will make it "
                    "available here automatically."
                ),
                width=40,
            )

            return

        selected_descriptor = (
            _descriptor_for_selection(
                stage,
                current_id,
            )
        )

        selection_box = (
            layout.box()
        )

        header = (
            selection_box.row()
        )

        header.label(
            text="Implementation",
            icon="SETTINGS",
        )

        if selected_descriptor is not None:
            selected = (
                selection_box.row(
                    align=True
                )
            )

            selected.label(
                text=(
                    selected_descriptor.label
                ),
                icon="CHECKMARK",
            )

            version = (
                selected.row()
            )

            version.alignment = (
                "RIGHT"
            )

            version.label(
                text=(
                    f"v{selected_descriptor.version}"
                )
            )

            if (
                selected_descriptor
                .description
            ):
                _draw_wrapped_text(
                    selection_box,
                    selected_descriptor
                    .description,
                    width=40,
                )

        else:
            warning = (
                selection_box.row()
            )

            warning.alert = True

            warning.label(
                text=(
                    "Select an implementation"
                ),
                icon="ERROR",
            )

        # -------------------------------------------------
        # Only show implementation choices when there is
        # something to choose.
        # -------------------------------------------------

        if (
            len(descriptors) > 1
            or selected_descriptor
            is None
        ):
            selection_box.separator()

            for descriptor in (
                descriptors
            ):
                is_selected = (
                    descriptor.identifier
                    == current_id
                )

                row = (
                    selection_box.row()
                )

                operator = row.operator(
                    (
                        "bpt."
                        "set_pipeline_implementation"
                    ),
                    text=(
                        descriptor.label
                    ),
                    icon=(
                        "CHECKMARK"
                        if is_selected
                        else "NONE"
                    ),
                    depress=(
                        is_selected
                    ),
                )

                operator.stage = (
                    stage.value
                )

                operator.implementation_id = (
                    descriptor.identifier
                )

                operator.enable_stage = True

    # -----------------------------------------------------
    # Implementation settings dispatch
    # -----------------------------------------------------

    def _draw_implementation_settings(
        self,
        layout,
        context: bpy.types.Context,
        settings,
        stage: PipelineStage,
        implementation_id: str,
    ) -> None:
        """
        Generic UI extension mechanism.

        Future implementations can optionally implement:

            draw_settings(layout, context)

        without modifying this central panel.

        Built-in implementations which predate this optional
        hook have small compatibility drawers below.
        """

        implementation = (
            PIPELINE_REGISTRY
            .get(
                implementation_id
            )
        )

        if implementation is not None:
            custom_draw = getattr(
                implementation,
                "draw_settings",
                None,
            )

            if callable(
                custom_draw
            ):
                try:
                    custom_draw(
                        layout,
                        context,
                    )

                except Exception as exc:
                    warning = (
                        layout.box()
                    )

                    warning.alert = True

                    warning.label(
                        text=(
                            "Implementation UI failed"
                        ),
                        icon="ERROR",
                    )

                    _draw_wrapped_text(
                        warning,
                        str(
                            exc
                        ),
                    )

                return

        # -------------------------------------------------
        # Current built-in compatibility drawers.
        # -------------------------------------------------

        if (
            implementation_id
            == "projection-images"
        ):
            self._draw_projection_input(
                layout,
                settings,
            )

            return

        if (
            implementation_id
            == "native-visual-hull"
        ):
            self._draw_native_geometry(
                layout,
                settings,
            )

            return

        if (
            implementation_id
            == "projected-color-v1.2"
        ):
            self._draw_projected_material(
                layout,
                implementation,
            )

            return

        # -------------------------------------------------
        # Generic fallback.
        # -------------------------------------------------

        if implementation is not None:
            descriptor = (
                implementation
                .descriptor
            )

            if descriptor.capabilities:
                capability_box = (
                    layout.box()
                )

                capability_box.label(
                    text="Capabilities",
                    icon="INFO",
                )

                for capability in (
                    descriptor.capabilities
                ):
                    capability_box.label(
                        text=(
                            capability
                        )
                    )

        else:
            warning = (
                layout.box()
            )

            warning.alert = True

            warning.label(
                text=(
                    "Implementation unavailable"
                ),
                icon="ERROR",
            )

    # -----------------------------------------------------
    # INPUT
    # -----------------------------------------------------
