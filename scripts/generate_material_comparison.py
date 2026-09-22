from __future__ import annotations

"""CLI and compatibility facade for material-comparison generation.

The implementation lives in scripts.material_comparison_generator. Keep the
established imports here because benchmark_uv_bake_resolution.py uses them.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.material_comparison_generator.adapters import (
    build_geometry_output,
    build_material_settings,
    build_projection_source,
    create_material_implementation,
    execute_material,
)
from scripts.material_comparison_generator.cli import (
    _script_arguments,
    parse_args,
    validate_args,
)
from scripts.material_comparison_generator.config import (
    DEFAULT_ALPHA_THRESHOLD,
    DEFAULT_ANGLE_LIMIT_DEGREES,
    DEFAULT_EXAMPLE_DIR,
    DEFAULT_ISLAND_MARGIN,
    DEFAULT_MESH_MODE,
    DEFAULT_PADDING_PIXELS,
    DEFAULT_PROFILES,
    DEFAULT_RESOLUTION,
    DEFAULT_SAMPLES_PER_AXIS,
    DEFAULT_SHEET_WHITE_THRESHOLD,
    DEFAULT_TARGET_HEIGHT,
    DEFAULT_TEXTURE_SIZE,
    DEFAULT_UV_LAYER_NAME,
    DEFAULT_VOXEL_SIZE,
    SUPPORTED_IMPLEMENTATIONS,
    PipelineRuntime,
    load_pipeline_runtime,
)
from scripts.material_comparison_generator.io import (
    discover_sheets,
    json_safe,
    write_json,
)
from scripts.material_comparison_generator.lifecycle import cleanup_object
from scripts.material_comparison_generator.runner import main
from scripts.material_comparison_generator.sheet import process_sheet
from scripts.material_comparison_generator.variant import generate_variant


if __name__ == "__main__":
    main()