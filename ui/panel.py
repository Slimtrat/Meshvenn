from __future__ import annotations

from bpy.types import Panel

from .actions import StageActionsMixin
from .advanced import AdvancedMixin
from .diagnostics import DiagnosticsMixin
from .drawers import ImplementationDrawersMixin
from .stage_cards import StageCardsMixin


class BPT_PT_MainPanel(
    StageCardsMixin,
    ImplementationDrawersMixin,
    StageActionsMixin,
    DiagnosticsMixin,
    AdvancedMixin,
    Panel,
):
    bl_label = "Meshvenn"
    bl_idname = "BPT_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Meshvenn"
