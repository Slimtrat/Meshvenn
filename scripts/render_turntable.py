"""Render a GLB turntable and contact sheet.

Public helper imports remain here for projection-sheet and comparison scripts.
"""
from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.render_turntable_support.arguments import parse_args
from scripts.render_turntable_support.scene import (
    clear_scene, import_glb, imported_material_summary, print_material_summary,
    combined_bounds, center_objects, ensure_preview_material,
    validate_preserved_materials,
)
from scripts.render_turntable_support.camera import (
    look_at, create_camera, create_area_light, setup_lighting, setup_render,
)
from scripts.render_turntable_support.render import (
    view_angles, place_camera, render_views, build_contact_sheet,
)
from scripts.render_turntable_support.pipeline import render_turntable, main

if __name__ == "__main__":
    main()
