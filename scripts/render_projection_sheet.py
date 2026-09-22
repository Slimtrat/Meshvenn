"""Render reconstructed GLB views into the Projection Tool sheet template."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.render_projection_sheet_support.source import CELL_INSET, parse_args, load_sheet
from scripts.render_projection_sheet_support.layout import inset_bbox, build_cells, clear_cell
from scripts.render_projection_sheet_support.camera import (
    common_ortho_scale, place_projection_camera, configure_projection_render,
)
from scripts.render_projection_sheet_support.render import render_view, composite_view, save_sheet
from scripts.render_projection_sheet_support.pipeline import main

if __name__ == "__main__":
    main()
