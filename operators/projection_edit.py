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

from .constants import ANGLE_PATTERN, IMAGE_FILTER
from .runtime import clear_pipeline_runtime_state
# ---------------------------------------------------------
# Projection management
# ---------------------------------------------------------

class BPT_OT_AddProjection(
    Operator
):
    bl_idname = (
        "bpt.add_projection"
    )

    bl_label = (
        "Add Projection"
    )

    bl_description = (
        "Add a new arbitrary projection view"
    )

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        projection = (
            settings
            .projections
            .add()
        )

        projection.name = (
            "Projection "
            f"{len(settings.projections)}"
        )

        projection.azimuth = 0.0

        projection.elevation = 0.0

        projection.enabled = True

        projection.flip_x = False

        settings.active_projection_index = (
            len(
                settings.projections
            )
            - 1
        )

        clear_pipeline_runtime_state(
            context.scene
        )

        return {
            "FINISHED"
        }


class BPT_OT_RemoveProjection(
    Operator
):
    bl_idname = (
        "bpt.remove_projection"
    )

    bl_label = (
        "Remove Projection"
    )

    bl_description = (
        "Remove the selected projection"
    )

    index: IntProperty()

    def execute(
        self,
        context: bpy.types.Context,
    ) -> set[str]:
        settings = (
            context
            .scene
            .bpt_settings
        )

        if not settings.projections:
            return {
                "CANCELLED"
            }

        index = min(
            max(
                self.index,
                0,
            ),
            len(
                settings.projections
            )
            - 1,
        )

        settings.projections.remove(
            index
        )

        if settings.projections:
            settings.active_projection_index = (
                min(
                    index,
                    len(
                        settings.projections
                    )
                    - 1,
                )
            )

        else:
            settings.active_projection_index = 0

        clear_pipeline_runtime_state(
            context.scene
        )

        return {
            "FINISHED"
        }


# ---------------------------------------------------------
# Projection presets
# ---------------------------------------------------------

def _extract_angle_from_name(
    name: str,
) -> float | None:
    match = (
        ANGLE_PATTERN
        .search(
            name
        )
    )

    if not match:
        lowered = (
            name.lower()
        )

        if "front" in lowered:
            return 0.0

        if (
            "right" in lowered
            or "side" in lowered
        ):
            return 90.0

        if "back" in lowered:
            return 180.0

        if "left" in lowered:
            return 270.0

        return None

    return float(
        int(
            match.group(1)
        )
        % 360
    )


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------
