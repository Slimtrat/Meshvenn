from __future__ import annotations

import bpy

from .panel import BPT_PT_MainPanel
from .projection_list import BPT_UL_ProjectionViews

CLASSES = (
    BPT_UL_ProjectionViews,
    BPT_PT_MainPanel,
)


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------

def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(
            cls
        )


def unregister() -> None:
    for cls in reversed(
        CLASSES
    ):
        bpy.utils.unregister_class(
            cls
        )
