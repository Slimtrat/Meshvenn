from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Keep the historical import surface for callers of this script.
from scripts.benchmark_uv_bake_support.shared import (
    Any,
    BACKGROUND_COLOR,
    BenchmarkVariant,
    DEFAULT_ALPHA_THRESHOLD,
    DEFAULT_ANGLE_LIMIT_DEGREES,
    DEFAULT_EXAMPLE_DIR,
    DEFAULT_GEOMETRY_RESOLUTION,
    DEFAULT_GUTTER,
    DEFAULT_ISLAND_MARGIN,
    DEFAULT_MAX_SUBPIXEL_RATIO,
    DEFAULT_MESH_MODE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PADDING_PIXELS,
    DEFAULT_PROFILES,
    DEFAULT_RENDER_SAMPLES,
    DEFAULT_RENDER_SIZE,
    DEFAULT_RENDER_VIEWS,
    DEFAULT_SAMPLES_PER_AXIS,
    DEFAULT_SHEET_WHITE_THRESHOLD,
    DEFAULT_TARGET_HEIGHT,
    DEFAULT_TEXTURE_SIZES,
    DEFAULT_UV_LAYER_NAME,
    DEFAULT_VOXEL_SIZE,
    IMAGE_DIFF_THRESHOLD,
    NativeScanner,
    PROJECTED_IMPLEMENTATION_ID,
    Path,
    REPO_ROOT,
    RunLogger,
    UV_IMPLEMENTATION_ID,
    argparse,
    array,
    bpy,
    build_geometry_output,
    build_material_settings,
    build_projection_source,
    cleanup_object,
    clear_scene,
    create_blender_mesh_from_native,
    dataclass,
    execute_material,
    export_object,
    extract_sheet,
    json,
    load_pipeline_runtime,
    material_views_for_snapshot,
    math,
    prepare_material_views,
    prepare_projections,
    render_turntable,
    scale_object_to_height,
    shade_smooth_native_object,
    shutil,
    sys,
    time,
)
from scripts.benchmark_uv_bake_support.cli import (
    _script_arguments,
    parse_args,
    _unique_ordered,
    validate_args,
)
from scripts.benchmark_uv_bake_support.material import (
    material_diagnostics,
    save_baked_texture,
)
from scripts.benchmark_uv_bake_support.variant import (
    variant_args,
    generate_variant,
)
from scripts.benchmark_uv_bake_support.geometry import (
    geometry_signature,
    validate_geometry_parity,
)
from scripts.benchmark_uv_bake_support.render import (
    render_variant,
    load_image_pixels,
    compare_render_images,
    compare_with_baseline,
)
from scripts.benchmark_uv_bake_support.matrix import (
    compose_matrix,
)
from scripts.benchmark_uv_bake_support.report import (
    benchmark_row,
    _percent,
    _seconds,
    _mib,
    _float_value,
    write_markdown,
)
from scripts.benchmark_uv_bake_support.recommendation import (
    recommend_resolution,
)
from scripts.benchmark_uv_bake_support.discovery import (
    discover_sheets,
)
from scripts.benchmark_uv_bake_support.runner import (
    benchmark_profile,
    benchmark_sheet,
)
from scripts.benchmark_uv_bake_support.entrypoint import (
    print_results,
    main,
)
from scripts.benchmark_uv_bake_support.artifacts import (
    write_json,
)

if __name__ == "__main__":
    main()
