from __future__ import annotations

import math

import bpy

from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from ..core.pipeline_contracts import (
    PipelinePlan,
    PipelineStage,
    PipelineStageSelection,
)

from .groups import BPT_PG_Settings
from .pipeline import ensure_pipeline_defaults

def ensure_default_projections(
    settings: BPT_PG_Settings,
) -> None:
    if len(
        settings.projections
    ) > 0:
        return

    defaults = (
        (
            "Front",
            0.0,
            0.0,
            False,
        ),
        (
            "Right",
            90.0,
            0.0,
            False,
        ),
        (
            "Back",
            180.0,
            0.0,
            False,
        ),
        (
            "Top",
            0.0,
            90.0,
            False,
        ),
    )

    for (
        name,
        azimuth_deg,
        elevation_deg,
        flip_x,
    ) in defaults:
        item = (
            settings
            .projections
            .add()
        )

        item.name = (
            name
        )

        item.azimuth = (
            math.radians(
                azimuth_deg
            )
        )

        item.elevation = (
            math.radians(
                elevation_deg
            )
        )

        item.flip_x = (
            flip_x
        )

        item.enabled = (
            name
            in {
                "Front",
                "Right",
            }
        )


# =========================================================
# Scene initialization
# =========================================================

def ensure_scene_defaults(
    scene: bpy.types.Scene,
) -> None:
    settings = getattr(
        scene,
        "bpt_settings",
        None,
    )

    if settings is None:
        return

    ensure_default_projections(
        settings
    )

    ensure_pipeline_defaults(
        settings
    )


def _ensure_scene_defaults() -> None:
    """
    Timer callback used after add-on registration.

    Initialize every loaded scene rather than only the active
    scene so switching scenes cannot expose an uninitialized
    pipeline.
    """

    for scene in tuple(
        bpy.data.scenes
    ):
        ensure_scene_defaults(
            scene
        )
