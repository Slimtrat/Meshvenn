"""CLI and compatibility facade for rendering material comparisons."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.material_comparison_render.cli import (
    _script_arguments,
    _unique_ordered,
    parse_args,
    validate_args,
)
from scripts.material_comparison_render.config import (
    BACKGROUND_COLOR,
    DEFAULT_COMPARISON_ROOT,
    DEFAULT_GUTTER,
    DEFAULT_IMPLEMENTATIONS,
    DEFAULT_PROFILES,
    DEFAULT_SAMPLES,
    DEFAULT_SIZE,
    DEFAULT_VIEWS,
    DIMENSION_TOLERANCE,
    Variant,
)
from scripts.material_comparison_render.images import (
    _image_size,
    _load_image_pixels,
)
from scripts.material_comparison_render.matrix import build_comparison_matrix
from scripts.material_comparison_render.render import render_variant
from scripts.material_comparison_render.runner import main, write_markdown_index
from scripts.material_comparison_render.sheet import process_sheet
from scripts.material_comparison_render.variants import (
    _geometry_signature,
    discover_sheets,
    load_variant,
    read_json,
    validate_geometry_parity,
    write_json,
)
from scripts.render_turntable import render_turntable


if __name__ == "__main__":
    main()