from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time

from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpy


# =========================================================
# Repository
# =========================================================

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)
from core.native_scan import (
    NativeScanner,
)

from scripts.generate_example_native import (
    clear_scene,
    export_object,
    extract_sheet,
    material_views_for_snapshot,
    prepare_material_views,
    prepare_projections,
    scale_object_to_height,
)

from scripts.generate_material_comparison import (
    build_geometry_output,
    build_material_settings,
    build_projection_source,
    cleanup_object,
    execute_material,
    load_pipeline_runtime,
)

from scripts.render_turntable import (
    render_turntable,
)

from scripts.run_logger import (
    RunLogger,
)


# =========================================================
# Defaults
# =========================================================

DEFAULT_EXAMPLE_DIR = (
    REPO_ROOT
    / "example"
    / "mascotte"
    / "test1"
)

DEFAULT_OUTPUT_DIR = (
    DEFAULT_EXAMPLE_DIR
    / "uv-bake-resolution-benchmark"
)

DEFAULT_PROFILES = (
    "L2",
    "L10",
)

DEFAULT_TEXTURE_SIZES = (
    256,
    512,
    1024,
)

DEFAULT_GEOMETRY_RESOLUTION = 64

DEFAULT_MESH_MODE = (
    "surface_nets"
)

DEFAULT_PADDING_PIXELS = 4

DEFAULT_SAMPLES_PER_AXIS = 1

DEFAULT_RENDER_SIZE = 256

DEFAULT_RENDER_VIEWS = 4

DEFAULT_RENDER_SAMPLES = 1

DEFAULT_TARGET_HEIGHT = 2.0

DEFAULT_ALPHA_THRESHOLD = 0.1

DEFAULT_SHEET_WHITE_THRESHOLD = 0.94

DEFAULT_VOXEL_SIZE = 1.0

DEFAULT_UV_LAYER_NAME = (
    "MeshvennBenchmarkUV"
)

DEFAULT_ISLAND_MARGIN = 0.02

DEFAULT_ANGLE_LIMIT_DEGREES = 66.0

DEFAULT_MAX_SUBPIXEL_RATIO = 0.10

DEFAULT_GUTTER = 8

PROJECTED_IMPLEMENTATION_ID = (
    "projected-color-v1.2"
)

UV_IMPLEMENTATION_ID = (
    "uv-bake-v2"
)

BACKGROUND_COLOR = (
    0.025,
    0.025,
    0.030,
    1.0,
)

IMAGE_DIFF_THRESHOLD = (
    1.0
    / 255.0
)


# =========================================================
# Types
# =========================================================

@dataclass
class BenchmarkVariant:
    sheet: str

    profile: str

    implementation: str

    texture_size: int | None

    root: Path

    model_path: Path

    manifest_path: Path

    render_root: Path

    contact_sheet_path: Path

    info: dict[str, Any]

    render_seconds: float = 0.0

    rgb_mae_vs_baseline: float | None = None

    rgb_rmse_vs_baseline: float | None = None

    psnr_vs_baseline: float | None = None

    changed_pixel_ratio_vs_baseline: float | None = None
