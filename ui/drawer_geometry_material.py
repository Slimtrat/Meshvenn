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
class GeometryMaterialDrawerMixin:
    def _draw_native_geometry(
        self,
        layout,
        settings,
    ) -> None:
        quality = (
            layout.box()
        )

        quality.label(
            text="Reconstruction",
            icon="MESH_DATA",
        )

        quality.prop(
            settings,
            "resolution",
            text="Resolution",
            slider=True,
        )

        quality.prop(
            settings,
            "symmetry_x",
            text="Symmetry X",
        )

        quality.label(
            text=(
                "Surface: Surface Nets"
            ),
            icon="INFO",
        )

        performance = (
            layout.box()
        )

        performance.label(
            text="Performance",
            icon="TIME",
        )

        performance.prop(
            settings,
            "thread_count",
            text="Threads",
        )

        if (
            settings.thread_count
            == 0
        ):
            performance.label(
                text=(
                    "0 = automatic CPU detection"
                ),
                icon="INFO",
            )

        output = (
            layout.box()
        )

        output.label(
            text="Output",
            icon="OBJECT_DATA",
        )

        output.prop(
            settings,
            "normalize_height",
            text="Normalize Height",
        )

        if settings.normalize_height:
            output.prop(
                settings,
                "target_height",
                text="Target Height",
            )

    # -----------------------------------------------------
    # MATERIAL
    # -----------------------------------------------------

    def _draw_projected_material(
        self,
        layout,
        implementation,
    ) -> None:
        info = (
            layout.box()
        )

        info.label(
            text="Projected Color V1.2",
            icon="MATERIAL",
        )

        info.label(
            text="Visibility-aware projection",
            icon="CHECKMARK",
        )

        info.label(
            text="Adaptive multi-view blend",
            icon="CHECKMARK",
        )

        info.label(
            text="Top-K contributors",
            icon="CHECKMARK",
        )

        info.label(
            text="Backface safety fallback",
            icon="CHECKMARK",
        )

        if implementation is not None:
            descriptor = (
                implementation
                .descriptor
            )

            if descriptor.capabilities:
                capabilities = (
                    layout.box()
                )

                capabilities.label(
                    text="Capabilities",
                    icon="INFO",
                )

                for capability in (
                    descriptor.capabilities
                ):
                    capabilities.label(
                        text=capability,
                    )

        defaults = (
            layout.box()
        )

        defaults.label(
            text="Current Defaults",
            icon="SETTINGS",
        )

        defaults.label(
            text=(
                "Min facing: 0.10"
            )
        )

        defaults.label(
            text=(
                "Relative cutoff: 0.20"
            )
        )

        defaults.label(
            text=(
                "Max contributors: 3"
            )
        )

        defaults.label(
            text=(
                "Weight power: 1.5"
            )
        )

    # -----------------------------------------------------
    # Stage action
    # -----------------------------------------------------
