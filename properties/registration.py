from __future__ import annotations

import bpy
from bpy.props import PointerProperty

from .defaults import _ensure_scene_defaults
from .groups import (
    BPT_PG_PipelineSettings,
    BPT_PG_PipelineStageSettings,
    BPT_PG_ProjectionView,
    BPT_PG_Settings,
)

CLASSES = (
    BPT_PG_ProjectionView,

    BPT_PG_PipelineStageSettings,

    BPT_PG_PipelineSettings,

    BPT_PG_Settings,
)


# =========================================================
# Registration
# =========================================================

def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(
            cls
        )

    bpy.types.Scene.bpt_settings = (
        PointerProperty(
            type=BPT_PG_Settings,
        )
    )

    if not bpy.app.timers.is_registered(
        _ensure_scene_defaults
    ):
        bpy.app.timers.register(
            _ensure_scene_defaults,
            first_interval=0.1,
        )


def unregister() -> None:
    if bpy.app.timers.is_registered(
        _ensure_scene_defaults
    ):
        bpy.app.timers.unregister(
            _ensure_scene_defaults
        )

    if hasattr(
        bpy.types.Scene,
        "bpt_settings",
    ):
        del bpy.types.Scene.bpt_settings

    for cls in reversed(
        CLASSES
    ):
        bpy.utils.unregister_class(
            cls
        )
