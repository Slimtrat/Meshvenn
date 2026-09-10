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
    .parents[1]
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


# =========================================================
# CLI
# =========================================================

def _script_arguments() -> list[str]:
    if "--" not in sys.argv:
        return []

    index = sys.argv.index(
        "--"
    )

    return sys.argv[
        index + 1:
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark Meshvenn UV Bake V2 at several "
            "texture resolutions using identical geometry."
        )
    )

    parser.add_argument(
        "--example-dir",
        type=Path,
        default=DEFAULT_EXAMPLE_DIR,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--sheets",
        nargs="+",
        default=[
            "sheet1",
        ],
    )

    parser.add_argument(
        "--profiles",
        nargs="+",
        default=list(
            DEFAULT_PROFILES
        ),
    )

    parser.add_argument(
        "--texture-sizes",
        nargs="+",
        type=int,
        default=list(
            DEFAULT_TEXTURE_SIZES
        ),
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=(
            DEFAULT_GEOMETRY_RESOLUTION
        ),
    )

    parser.add_argument(
        "--mesh-mode",
        choices=(
            "surface_nets",
            "blocks",
        ),
        default=DEFAULT_MESH_MODE,
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=(
            DEFAULT_ALPHA_THRESHOLD
        ),
    )

    parser.add_argument(
        "--sheet-white-threshold",
        type=float,
        default=(
            DEFAULT_SHEET_WHITE_THRESHOLD
        ),
    )

    parser.add_argument(
        "--thread-count",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--symmetry-x",
        action="store_true",
    )

    parser.add_argument(
        "--voxel-size",
        type=float,
        default=(
            DEFAULT_VOXEL_SIZE
        ),
    )

    parser.add_argument(
        "--target-height",
        type=float,
        default=(
            DEFAULT_TARGET_HEIGHT
        ),
    )

    parser.add_argument(
        "--padding",
        type=int,
        default=(
            DEFAULT_PADDING_PIXELS
        ),
    )

    parser.add_argument(
        "--samples-per-axis",
        type=int,
        choices=(
            1,
            2,
            3,
            4,
        ),
        default=(
            DEFAULT_SAMPLES_PER_AXIS
        ),
    )

    parser.add_argument(
        "--uv-layer-name",
        default=(
            DEFAULT_UV_LAYER_NAME
        ),
    )

    parser.add_argument(
        "--island-margin",
        type=float,
        default=(
            DEFAULT_ISLAND_MARGIN
        ),
    )

    parser.add_argument(
        "--angle-limit",
        type=float,
        default=(
            DEFAULT_ANGLE_LIMIT_DEGREES
        ),
    )

    parser.add_argument(
        "--render-size",
        type=int,
        default=(
            DEFAULT_RENDER_SIZE
        ),
    )

    parser.add_argument(
        "--views",
        type=int,
        default=(
            DEFAULT_RENDER_VIEWS
        ),
    )

    parser.add_argument(
        "--render-samples",
        type=int,
        default=(
            DEFAULT_RENDER_SAMPLES
        ),
    )

    parser.add_argument(
        "--max-subpixel-ratio",
        type=float,
        default=(
            DEFAULT_MAX_SUBPIXEL_RATIO
        ),
        help=(
            "Technical target used when suggesting the "
            "smallest acceptable UV resolution."
        ),
    )

    parser.add_argument(
        "--gutter",
        type=int,
        default=(
            DEFAULT_GUTTER
        ),
    )

    parser.add_argument(
        "--save-blend",
        action="store_true",
    )

    parser.add_argument(
        "--keep-stills",
        action="store_true",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args(
        _script_arguments()
    )


# =========================================================
# Validation
# =========================================================

def _unique_ordered(
    values,
) -> list:
    result = []

    for value in values:
        if value not in result:
            result.append(
                value
            )

    return result


def validate_args(
    args: argparse.Namespace,
) -> None:
    if not (
        8
        <= args.resolution
        <= 256
    ):
        raise ValueError(
            (
                "Geometry resolution must "
                "be between 8 and 256."
            )
        )

    args.profiles = (
        _unique_ordered(
            [
                str(profile)
                .strip()
                .upper()
                for profile
                in args.profiles
            ]
        )
    )

    for profile in args.profiles:
        if profile not in {
            "L2",
            "L4",
            "L8",
            "L10",
        }:
            raise ValueError(
                (
                    "Unsupported profile: "
                    f"{profile}"
                )
            )

    if not args.profiles:
        raise ValueError(
            (
                "At least one profile "
                "is required."
            )
        )

    args.texture_sizes = (
        sorted(
            set(
                args.texture_sizes
            )
        )
    )

    allowed_texture_sizes = {
        64,
        128,
        256,
        512,
        1024,
        2048,
        4096,
    }

    if not args.texture_sizes:
        raise ValueError(
            (
                "At least one texture "
                "size is required."
            )
        )

    for texture_size in (
        args.texture_sizes
    ):
        if (
            texture_size
            not in allowed_texture_sizes
        ):
            raise ValueError(
                (
                    "Unsupported texture size: "
                    f"{texture_size}"
                )
            )

    if not (
        0
        <= args.padding
        <= 128
    ):
        raise ValueError(
            (
                "Padding must be "
                "between 0 and 128."
            )
        )

    if not (
        4
        <= args.views
        <= 16
    ):
        raise ValueError(
            (
                "Views must be "
                "between 4 and 16."
            )
        )

    if args.render_size < 128:
        raise ValueError(
            (
                "Render size must "
                "be >= 128."
            )
        )

    if args.render_samples < 1:
        raise ValueError(
            (
                "Render samples must "
                "be >= 1."
            )
        )

    if not (
        0.0
        <= args.max_subpixel_ratio
        <= 1.0
    ):
        raise ValueError(
            (
                "max-subpixel-ratio must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        <= args.threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Alpha threshold must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        <= args.sheet_white_threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Sheet white threshold must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        <= args.island_margin
        <= 1.0
    ):
        raise ValueError(
            (
                "Island margin must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        < args.angle_limit
        <= 90.0
    ):
        raise ValueError(
            (
                "Angle limit must "
                "be inside ]0, 90]."
            )
        )

    if args.voxel_size <= 0.0:
        raise ValueError(
            (
                "Voxel size must "
                "be positive."
            )
        )

    if args.target_height <= 0.0:
        raise ValueError(
            (
                "Target height must "
                "be positive."
            )
        )


# =========================================================
# JSON
# =========================================================

def write_json(
    path: Path,
    value: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# =========================================================
# Arguments for one MATERIAL execution
# =========================================================

def variant_args(
    args: argparse.Namespace,
    *,
    texture_size: int,
) -> argparse.Namespace:
    values = dict(
        vars(
            args
        )
    )

    values[
        "texture_size"
    ] = (
        texture_size
    )

    return argparse.Namespace(
        **values
    )


# =========================================================
# Material result extraction
# =========================================================

def material_diagnostics(
    result,
) -> dict[str, Any]:
    payload = (
        result.payload
    )

    diagnostics: dict[
        str,
        Any,
    ] = {}

    bake_result = getattr(
        payload,
        "bake_result",
        None,
    )

    if bake_result is not None:
        stats = (
            bake_result.stats
        )

        diagnostics[
            "uv_bake"
        ] = {
            "texture_width": (
                bake_result
                .texture
                .width
            ),

            "texture_height": (
                bake_result
                .texture
                .height
            ),

            "triangle_count": (
                stats.triangle_count
            ),

            "rasterized_triangles": (
                stats
                .rasterized_triangles
            ),

            "degenerate_triangles": (
                stats
                .degenerate_triangles
            ),

            "covered_pixels": (
                stats.covered_pixels
            ),

            "padded_pixels": (
                stats.padded_pixels
            ),

            "overlap_pixels": (
                stats.overlap_pixels
            ),

            "surface_samples": (
                stats.surface_samples
            ),

            "fallback_samples": (
                stats.fallback_samples
            ),

            "selected_source_samples": (
                stats
                .selected_source_samples
            ),

            "coverage_ratio": (
                stats.coverage_ratio
            ),

            "filled_pixels": (
                stats.filled_pixels
            ),

            "filled_ratio": (
                float(
                    stats.filled_pixels
                )
                / float(
                    stats.texture_pixels
                )
                if stats.texture_pixels
                else 0.0
            ),
        }

    projected_stats = getattr(
        payload,
        "stats",
        None,
    )

    if projected_stats is not None:
        diagnostics[
            "projected_color"
        ] = {
            "vertex_count": (
                projected_stats
                .vertex_count
            ),

            "view_count": (
                projected_stats
                .view_count
            ),

            "projected_vertices": (
                projected_stats
                .projected_vertices
            ),

            "fallback_vertices": (
                projected_stats
                .fallback_vertices
            ),

            "visible_samples": (
                projected_stats
                .visible_samples
            ),

            "occluded_samples": (
                projected_stats
                .occluded_samples
            ),

            "selected_samples": (
                projected_stats
                .selected_samples
            ),
        }

    return diagnostics


# =========================================================
# Texture export
# =========================================================

def save_baked_texture(
    payload,
    output_path: Path,
) -> Path | None:
    image = getattr(
        payload,
        "image",
        None,
    )

    if image is None:
        return None

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image.filepath_raw = str(
        output_path.resolve()
    )

    image.file_format = (
        "PNG"
    )

    image.save()

    if not output_path.is_file():
        raise RuntimeError(
            (
                "Baked texture was "
                "not written: "
                f"{output_path}"
            )
        )

    return output_path


# =========================================================
# One material variant
# =========================================================

def generate_variant(
    runtime,
    *,
    sheet_name: str,
    profile: str,
    implementation_id: str,
    texture_size: int,
    snapshot,
    source,
    variant_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> BenchmarkVariant:
    clear_scene()

    obj = None

    try:
        name = (
            "MeshvennBenchmark_"
            f"{sheet_name}_"
            f"{profile}_"
            f"{implementation_id}_"
            f"{texture_size}"
        )

        obj = (
            create_blender_mesh_from_native(
                snapshot.mesh,
                mesh_name=name,
                object_name=name,
            )
        )

        shade_smooth_native_object(
            obj
        )

        local_args = (
            variant_args(
                args,
                texture_size=(
                    texture_size
                ),
            )
        )

        geometry = (
            build_geometry_output(
                runtime,

                obj=obj,

                snapshot=snapshot,

                source=source,

                args=local_args,
            )
        )

        settings = (
            build_material_settings(
                local_args
            )
        )

        (
            result,
            material_seconds,
            availability,
        ) = (
            execute_material(
                runtime,

                implementation_id=(
                    implementation_id
                ),

                geometry=geometry,

                settings=settings,
            )
        )

        # Projection coordinates must stay native until
        # MATERIAL execution has finished.
        scale_object_to_height(
            obj,
            args.target_height,
        )

        obj[
            "meshvenn_benchmark"
        ] = True

        obj[
            "meshvenn_benchmark_sheet"
        ] = sheet_name

        obj[
            "meshvenn_benchmark_profile"
        ] = profile

        obj[
            "meshvenn_benchmark_material"
        ] = implementation_id

        obj[
            "meshvenn_benchmark_texture_size"
        ] = texture_size

        variant_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        texture_png = (
            save_baked_texture(
                result.payload,

                variant_root
                / "baked_texture.png",
            )
        )

        export_info = (
            export_object(
                obj,

                output_dir=(
                    variant_root
                ),

                stem="model",

                save_blend=bool(
                    args.save_blend
                ),
            )
        )

        model_path = (
            variant_root
            / "model.glb"
        )

        if not model_path.is_file():
            raise RuntimeError(
                (
                    "GLB export did not "
                    "produce model.glb."
                )
            )

        diagnostics = (
            material_diagnostics(
                result
            )
        )

        info = {
            "generated": True,

            "sheet": (
                sheet_name
            ),

            "profile": (
                profile
            ),

            "implementation": (
                implementation_id
            ),

            "texture_size": (
                texture_size
                if (
                    implementation_id
                    == UV_IMPLEMENTATION_ID
                )
                else None
            ),

            "material_seconds": (
                material_seconds
            ),

            "availability": {
                "state": (
                    availability
                    .state
                    .value
                ),

                "reason": (
                    availability.reason
                ),

                "details": (
                    availability.details
                ),
            },

            "result": {
                "message": (
                    result.message
                ),

                "metrics": (
                    result.metrics
                ),

                "metadata": (
                    result.metadata
                ),
            },

            "geometry": {
                "vertices": len(
                    obj.data.vertices
                ),

                "faces": len(
                    obj.data.polygons
                ),

                "dimensions": [
                    float(
                        value
                    )
                    for value
                    in obj.dimensions
                ],

                "occupied_voxels": (
                    snapshot
                    .volume
                    .occupied_count
                ),

                "mesh_mode": (
                    args.mesh_mode
                ),

                "resolution": (
                    args.resolution
                ),
            },

            **diagnostics,

            "texture_png": (
                str(
                    texture_png
                )
                if texture_png
                is not None
                else None
            ),

            "texture_png_bytes": (
                texture_png
                .stat()
                .st_size
                if texture_png
                is not None
                else None
            ),

            "export": (
                export_info
            ),

            "glb_bytes": (
                model_path
                .stat()
                .st_size
            ),
        }

        manifest_path = (
            variant_root
            / "variant.json"
        )

        write_json(
            manifest_path,
            info,
        )

        return BenchmarkVariant(
            sheet=(
                sheet_name
            ),

            profile=(
                profile
            ),

            implementation=(
                implementation_id
            ),

            texture_size=(
                texture_size
                if (
                    implementation_id
                    == UV_IMPLEMENTATION_ID
                )
                else None
            ),

            root=(
                variant_root
            ),

            model_path=(
                model_path
            ),

            manifest_path=(
                manifest_path
            ),

            render_root=(
                variant_root
                / "render"
            ),

            contact_sheet_path=(
                variant_root
                / "render"
                / "contact_sheet.png"
            ),

            info=(
                info
            ),
        )

    finally:
        cleanup_object(
            obj
        )


# =========================================================
# Geometry parity
# =========================================================

def geometry_signature(
    variant: BenchmarkVariant,
) -> tuple[
    int,
    int,
    tuple[
        float,
        float,
        float,
    ],
]:
    geometry = (
        variant
        .info[
            "geometry"
        ]
    )

    return (
        int(
            geometry[
                "vertices"
            ]
        ),

        int(
            geometry[
                "faces"
            ]
        ),

        tuple(
            round(
                float(
                    value
                ),
                6,
            )
            for value
            in geometry[
                "dimensions"
            ]
        ),
    )


def validate_geometry_parity(
    variants: list[
        BenchmarkVariant
    ],
) -> None:
    if not variants:
        return

    reference = (
        geometry_signature(
            variants[
                0
            ]
        )
    )

    for variant in (
        variants[
            1:
        ]
    ):
        current = (
            geometry_signature(
                variant
            )
        )

        if current != reference:
            raise RuntimeError(
                (
                    "Geometry changed during "
                    "UV resolution benchmark.\n"
                    f"Reference: {reference}\n"
                    f"{variant.profile}/"
                    f"{variant.texture_size}: "
                    f"{current}"
                )
            )


# =========================================================
# Render
# =========================================================

def render_variant(
    variant: BenchmarkVariant,
    *,
    args: argparse.Namespace,
) -> None:
    if (
        variant
        .render_root
        .exists()
    ):
        shutil.rmtree(
            variant
            .render_root
        )

    started_at = (
        time.perf_counter()
    )

    contact_path = (
        render_turntable(
            variant.model_path,

            variant.render_root,

            views=(
                args.views
            ),

            size=(
                args.render_size
            ),

            samples=(
                args.render_samples
            ),

            keep_stills=(
                args.keep_stills
            ),

            preserve_material=True,
        )
    )

    variant.render_seconds = (
        time.perf_counter()
        - started_at
    )

    variant.contact_sheet_path = (
        contact_path
    )

    if not contact_path.is_file():
        raise RuntimeError(
            (
                "Render did not produce "
                f"{contact_path}"
            )
        )


# =========================================================
# Image loading
# =========================================================

def load_image_pixels(
    path: Path,
) -> tuple[
    array,
    int,
    int,
]:
    image = (
        bpy.data.images.load(
            str(
                path.resolve()
            ),
            check_existing=False,
        )
    )

    try:
        image.update()

        width = int(
            image.size[
                0
            ]
        )

        height = int(
            image.size[
                1
            ]
        )

        pixels = (
            array(
                "f",
                [
                    0.0
                ],
            )
            * (
                width
                * height
                * 4
            )
        )

        image.pixels.foreach_get(
            pixels
        )

        return (
            pixels,
            width,
            height,
        )

    finally:
        bpy.data.images.remove(
            image
        )


# =========================================================
# Render comparison metrics
# =========================================================

def compare_render_images(
    reference_path: Path,
    candidate_path: Path,
) -> dict[str, float]:
    (
        reference,
        reference_width,
        reference_height,
    ) = (
        load_image_pixels(
            reference_path
        )
    )

    (
        candidate,
        candidate_width,
        candidate_height,
    ) = (
        load_image_pixels(
            candidate_path
        )
    )

    if (
        reference_width
        != candidate_width
        or reference_height
        != candidate_height
    ):
        raise RuntimeError(
            (
                "Cannot compare render "
                "images with different sizes."
            )
        )

    pixel_count = (
        reference_width
        * reference_height
    )

    channel_count = (
        pixel_count
        * 3
    )

    absolute_error = 0.0

    squared_error = 0.0

    changed_pixels = 0

    for pixel_index in range(
        pixel_count
    ):
        offset = (
            pixel_index
            * 4
        )

        pixel_changed = False

        for channel in range(
            3
        ):
            difference = abs(
                float(
                    reference[
                        offset
                        + channel
                    ]
                )
                - float(
                    candidate[
                        offset
                        + channel
                    ]
                )
            )

            absolute_error += (
                difference
            )

            squared_error += (
                difference
                * difference
            )

            if (
                difference
                > IMAGE_DIFF_THRESHOLD
            ):
                pixel_changed = True

        if pixel_changed:
            changed_pixels += 1

    mae = (
        absolute_error
        / float(
            channel_count
        )
    )

    mse = (
        squared_error
        / float(
            channel_count
        )
    )

    rmse = math.sqrt(
        mse
    )

    if mse <= 0.0:
        psnr = float(
            "inf"
        )

    else:
        psnr = (
            10.0
            * math.log10(
                1.0
                / mse
            )
        )

    return {
        "rgb_mae": (
            mae
        ),

        "rgb_rmse": (
            rmse
        ),

        "psnr": (
            psnr
        ),

        "changed_pixel_ratio": (
            float(
                changed_pixels
            )
            / float(
                pixel_count
            )
        ),
    }


# =========================================================
# Apply reference comparison
# =========================================================

def compare_with_baseline(
    baseline: BenchmarkVariant,
    candidate: BenchmarkVariant,
) -> None:
    metrics = (
        compare_render_images(
            baseline
            .contact_sheet_path,

            candidate
            .contact_sheet_path,
        )
    )

    candidate.rgb_mae_vs_baseline = (
        metrics[
            "rgb_mae"
        ]
    )

    candidate.rgb_rmse_vs_baseline = (
        metrics[
            "rgb_rmse"
        ]
    )

    candidate.psnr_vs_baseline = (
        metrics[
            "psnr"
        ]
    )

    candidate.changed_pixel_ratio_vs_baseline = (
        metrics[
            "changed_pixel_ratio"
        ]
    )


# =========================================================
# Matrix composition
# =========================================================

def compose_matrix(
    cells: dict[
        tuple[
            str,
            str,
        ],
        Path,
    ],
    *,
    profiles: list[str],
    columns: list[str],
    output_path: Path,
    gutter: int,
) -> None:
    paths = [
        path
        for path
        in cells.values()
        if path.is_file()
    ]

    if not paths:
        raise RuntimeError(
            (
                "No render images available "
                "for benchmark matrix."
            )
        )

    (
        first_pixels,
        tile_width,
        tile_height,
    ) = (
        load_image_pixels(
            paths[
                0
            ]
        )
    )

    del first_pixels

    column_count = len(
        columns
    )

    row_count = len(
        profiles
    )

    output_width = (
        tile_width
        * column_count
        + gutter
        * max(
            0,
            column_count - 1,
        )
    )

    output_height = (
        tile_height
        * row_count
        + gutter
        * max(
            0,
            row_count - 1,
        )
    )

    destination = (
        array(
            "f",
            BACKGROUND_COLOR,
        )
        * (
            output_width
            * output_height
        )
    )

    row_values = (
        tile_width
        * 4
    )

    for (
        profile_index,
        profile,
    ) in enumerate(
        profiles
    ):
        visual_row = (
            row_count
            - 1
            - profile_index
        )

        destination_y = (
            visual_row
            * (
                tile_height
                + gutter
            )
        )

        for (
            column_index,
            column,
        ) in enumerate(
            columns
        ):
            path = (
                cells.get(
                    (
                        profile,
                        column,
                    )
                )
            )

            if (
                path is None
                or not path.is_file()
            ):
                continue

            (
                source,
                width,
                height,
            ) = (
                load_image_pixels(
                    path
                )
            )

            if (
                width != tile_width
                or height
                != tile_height
            ):
                raise RuntimeError(
                    (
                        "Benchmark render dimensions "
                        "are inconsistent."
                    )
                )

            destination_x = (
                column_index
                * (
                    tile_width
                    + gutter
                )
            )

            for local_y in range(
                tile_height
            ):
                source_start = (
                    local_y
                    * row_values
                )

                source_end = (
                    source_start
                    + row_values
                )

                destination_start = (
                    (
                        (
                            destination_y
                            + local_y
                        )
                        * output_width
                        + destination_x
                    )
                    * 4
                )

                destination_end = (
                    destination_start
                    + row_values
                )

                destination[
                    destination_start:
                    destination_end
                ] = (
                    source[
                        source_start:
                        source_end
                    ]
                )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = (
        bpy.data.images.new(
            name=(
                "MeshvennUVResolutionBenchmark"
            ),

            width=(
                output_width
            ),

            height=(
                output_height
            ),

            alpha=True,
        )
    )

    try:
        image.pixels.foreach_set(
            destination
        )

        image.filepath_raw = str(
            output_path.resolve()
        )

        image.file_format = (
            "PNG"
        )

        image.save()

    finally:
        bpy.data.images.remove(
            image
        )


# =========================================================
# Result extraction
# =========================================================

def benchmark_row(
    variant: BenchmarkVariant,
) -> dict[str, Any]:
    info = (
        variant.info
    )

    result_metrics = (
        info
        .get(
            "result",
            {}
        )
        .get(
            "metrics",
            {}
        )
    )

    bake = (
        info.get(
            "uv_bake"
        )
    )

    if not isinstance(
        bake,
        dict,
    ):
        bake = {}

    return {
        "sheet": (
            variant.sheet
        ),

        "profile": (
            variant.profile
        ),

        "implementation": (
            variant
            .implementation
        ),

        "texture_size": (
            variant.texture_size
        ),

        "vertices": (
            info[
                "geometry"
            ][
                "vertices"
            ]
        ),

        "faces": (
            info[
                "geometry"
            ][
                "faces"
            ]
        ),

        "material_seconds": (
            info[
                "material_seconds"
            ]
        ),

        "render_seconds": (
            variant
            .render_seconds
        ),

        "glb_bytes": (
            info[
                "glb_bytes"
            ]
        ),

        "texture_png_bytes": (
            info.get(
                "texture_png_bytes"
            )
        ),

        "coverage_ratio": (
            bake.get(
                "coverage_ratio"
            )
        ),

        "filled_ratio": (
            bake.get(
                "filled_ratio"
            )
        ),

        "covered_pixels": (
            bake.get(
                "covered_pixels"
            )
        ),

        "filled_pixels": (
            bake.get(
                "filled_pixels"
            )
        ),

        "surface_samples": (
            bake.get(
                "surface_samples"
            )
        ),

        "fallback_samples": (
            bake.get(
                "fallback_samples"
            )
        ),

        "subpixel_triangle_ratio": (
            result_metrics.get(
                "uv_subpixel_triangle_ratio"
            )
        ),

        "mean_triangle_area_pixels": (
            result_metrics.get(
                "uv_mean_triangle_area_pixels"
            )
        ),

        "effective_island_margin_pixels": (
            info
            .get(
                "result",
                {}
            )
            .get(
                "metadata",
                {}
            )
            .get(
                "effective_island_margin_pixels"
            )
        ),

        "rgb_mae_vs_projected": (
            variant
            .rgb_mae_vs_baseline
        ),

        "rgb_rmse_vs_projected": (
            variant
            .rgb_rmse_vs_baseline
        ),

        "psnr_vs_projected": (
            variant
            .psnr_vs_baseline
        ),

        "changed_pixel_ratio_vs_projected": (
            variant
            .changed_pixel_ratio_vs_baseline
        ),

        "model": str(
            variant
            .model_path
        ),

        "render": str(
            variant
            .contact_sheet_path
        ),

        "texture": (
            info.get(
                "texture_png"
            )
        ),
    }


# =========================================================
# Technical resolution recommendation
# =========================================================

def recommend_resolution(
    rows: list[
        dict[str, Any]
    ],
    *,
    profiles: list[str],
    texture_sizes: list[int],
    max_subpixel_ratio: float,
) -> dict[str, Any]:
    """
    This is deliberately a technical candidate, not an
    aesthetic verdict.

    Select the smallest texture size for which every tested
    profile reaches the requested subpixel-triangle target.
    """

    uv_rows = [
        row
        for row
        in rows
        if (
            row[
                "implementation"
            ]
            == UV_IMPLEMENTATION_ID
        )
    ]

    for texture_size in (
        texture_sizes
    ):
        size_rows = {
            row[
                "profile"
            ]: row
            for row
            in uv_rows
            if (
                row[
                    "texture_size"
                ]
                == texture_size
            )
        }

        if any(
            profile
            not in size_rows
            for profile
            in profiles
        ):
            continue

        passes = True

        reasons = []

        for profile in profiles:
            row = (
                size_rows[
                    profile
                ]
            )

            subpixel = (
                row[
                    "subpixel_triangle_ratio"
                ]
            )

            coverage = (
                row[
                    "coverage_ratio"
                ]
            )

            if subpixel is None:
                passes = False

                reasons.append(
                    (
                        f"{profile}: missing "
                        "subpixel metric"
                    )
                )

            elif (
                float(
                    subpixel
                )
                > max_subpixel_ratio
            ):
                passes = False

                reasons.append(
                    (
                        f"{profile}: "
                        f"{float(subpixel) * 100.0:.2f}% "
                        "subpixel triangles"
                    )
                )

            if (
                coverage is None
                or float(
                    coverage
                )
                <= 0.0
            ):
                passes = False

                reasons.append(
                    (
                        f"{profile}: "
                        "invalid UV coverage"
                    )
                )

        if passes:
            return {
                "texture_size": (
                    texture_size
                ),

                "target_met": True,

                "max_subpixel_ratio": (
                    max_subpixel_ratio
                ),

                "reason": (
                    "Smallest tested texture size "
                    "meeting the subpixel target "
                    "for every tested profile."
                ),
            }

    return {
        "texture_size": (
            max(
                texture_sizes
            )
        ),

        "target_met": False,

        "max_subpixel_ratio": (
            max_subpixel_ratio
        ),

        "reason": (
            "No tested resolution met the subpixel "
            "target for every profile. The largest "
            "tested size is retained as the technical "
            "candidate."
        ),
    }


# =========================================================
# Markdown
# =========================================================

def _percent(
    value,
) -> str:
    if value is None:
        return "-"

    return (
        f"{float(value) * 100.0:.2f}%"
    )


def _seconds(
    value,
) -> str:
    if value is None:
        return "-"

    return (
        f"{float(value):.2f}s"
    )


def _mib(
    value,
) -> str:
    if value is None:
        return "-"

    return (
        f"{float(value) / (1024.0 * 1024.0):.2f}"
    )


def _float_value(
    value,
    digits: int = 4,
) -> str:
    if value is None:
        return "-"

    if (
        isinstance(
            value,
            float,
        )
        and math.isinf(
            value
        )
    ):
        return "∞"

    return (
        f"{float(value):.{digits}f}"
    )


def write_markdown(
    output_root: Path,
    *,
    rows: list[
        dict[str, Any]
    ],
    profiles: list[str],
    texture_sizes: list[int],
    recommendation: dict[str, Any],
) -> Path:
    path = (
        output_root
        / "BENCHMARK.md"
    )

    columns = [
        "Projected V1.2",
        *[
            f"UV {size}²"
            for size
            in texture_sizes
        ],
    ]

    lines = [
        "# Meshvenn — UV Bake Resolution Benchmark",
        "",
        "## Visual matrix",
        "",
        "Columns, left to right:",
        "",
        *[
            (
                f"{index}. `{column}`"
            )
            for (
                index,
                column,
            )
            in enumerate(
                columns,
                start=1,
            )
        ],
        "",
        "Rows, top to bottom:",
        "",
        *[
            (
                f"{index}. `{profile}`"
            )
            for (
                index,
                profile,
            )
            in enumerate(
                profiles,
                start=1,
            )
        ],
        "",
        "![UV Bake resolution benchmark](benchmark_matrix.png)",
        "",
        "## Metrics",
        "",
        (
            "| Profile | Variant | Bake | Coverage | "
            "Filled | Subpixel tris | Mean tri px² | "
            "GLB MiB | Texture MiB | RGB MAE vs projected | "
            "PSNR vs projected |"
        ),
        (
            "| --- | --- | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: | ---: |"
        ),
    ]

    for row in rows:
        if (
            row[
                "implementation"
            ]
            == PROJECTED_IMPLEMENTATION_ID
        ):
            label = (
                "Projected V1.2"
            )

        else:
            label = (
                "UV "
                f"{row['texture_size']}²"
            )

        lines.append(
            (
                f"| {row['profile']} "
                f"| {label} "
                f"| {_seconds(row['material_seconds'])} "
                f"| {_percent(row['coverage_ratio'])} "
                f"| {_percent(row['filled_ratio'])} "
                f"| {_percent(row['subpixel_triangle_ratio'])} "
                f"| {_float_value(row['mean_triangle_area_pixels'], 2)} "
                f"| {_mib(row['glb_bytes'])} "
                f"| {_mib(row['texture_png_bytes'])} "
                f"| {_float_value(row['rgb_mae_vs_projected'], 5)} "
                f"| {_float_value(row['psnr_vs_projected'], 2)} |"
            )
        )

    lines.extend(
        [
            "",
            "## Technical candidate",
            "",
            (
                "**Texture size:** "
                f"`{recommendation['texture_size']}²`"
            ),
            "",
            (
                "**Subpixel target:** "
                f"`{recommendation['max_subpixel_ratio'] * 100.0:.1f}%`"
            ),
            "",
            (
                "**Target met:** "
                f"`{recommendation['target_met']}`"
            ),
            "",
            recommendation[
                "reason"
            ],
            "",
            (
                "> This recommendation only evaluates UV "
                "sampling density and successful bake coverage. "
                "The final product default should also be chosen "
                "from the visual matrix."
            ),
            "",
        ]
    )

    path.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    return path


# =========================================================
# Sheet discovery
# =========================================================

def discover_sheets(
    example_dir: Path,
    names: list[str],
) -> list[Path]:
    sheets_dir = (
        example_dir
        / "sheets"
    )

    if not sheets_dir.is_dir():
        raise FileNotFoundError(
            (
                "Missing sheets directory: "
                f"{sheets_dir}"
            )
        )

    results = []

    for name in names:
        stem = (
            Path(
                name
            )
            .stem
        )

        path = (
            sheets_dir
            / f"{stem}.png"
        )

        if not path.is_file():
            raise FileNotFoundError(
                (
                    "Missing benchmark sheet: "
                    f"{path}"
                )
            )

        results.append(
            path
        )

    return results


# =========================================================
# One profile
# =========================================================

def benchmark_profile(
    runtime,
    *,
    sheet_name: str,
    profile: str,
    snapshot,
    source,
    sheet_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> tuple[
    BenchmarkVariant,
    list[
        BenchmarkVariant
    ],
]:
    profile_root = (
        sheet_root
        / profile
    )

    variants: list[
        BenchmarkVariant
    ] = []

    # -----------------------------------------------------
    # Projected Color baseline
    # -----------------------------------------------------

    baseline_root = (
        profile_root
        / PROJECTED_IMPLEMENTATION_ID
    )

    baseline = (
        generate_variant(
            runtime,

            sheet_name=(
                sheet_name
            ),

            profile=(
                profile
            ),

            implementation_id=(
                PROJECTED_IMPLEMENTATION_ID
            ),

            # Irrelevant to projected color, but required by
            # the shared settings adapter.
            texture_size=(
                args.texture_sizes[
                    0
                ]
            ),

            snapshot=(
                snapshot
            ),

            source=(
                source
            ),

            variant_root=(
                baseline_root
            ),

            args=(
                args
            ),

            logger=(
                logger
            ),
        )
    )

    render_variant(
        baseline,
        args=args,
    )

    variants.append(
        baseline
    )

    # -----------------------------------------------------
    # UV Bake sizes
    # -----------------------------------------------------

    for texture_size in (
        args.texture_sizes
    ):
        uv_root = (
            profile_root
            / UV_IMPLEMENTATION_ID
            / str(
                texture_size
            )
        )

        variant = (
            generate_variant(
                runtime,

                sheet_name=(
                    sheet_name
                ),

                profile=(
                    profile
                ),

                implementation_id=(
                    UV_IMPLEMENTATION_ID
                ),

                texture_size=(
                    texture_size
                ),

                snapshot=(
                    snapshot
                ),

                source=(
                    source
                ),

                variant_root=(
                    uv_root
                ),

                args=(
                    args
                ),

                logger=(
                    logger
                ),
            )
        )

        render_variant(
            variant,
            args=args,
        )

        compare_with_baseline(
            baseline,
            variant,
        )

        variants.append(
            variant
        )

    validate_geometry_parity(
        variants
    )

    return (
        baseline,
        variants[
            1:
        ],
    )


# =========================================================
# One sheet
# =========================================================

def benchmark_sheet(
    runtime,
    *,
    sheet_path: Path,
    output_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> tuple[
    list[
        BenchmarkVariant
    ],
    dict[
        tuple[
            str,
            str,
        ],
        Path,
    ],
]:
    sheet_name = (
        sheet_path.stem
    )

    sheet_root = (
        output_root
        / sheet_name
    )

    source_root = (
        sheet_root
        / "source"
    )

    with logger.section(
        f"benchmark {sheet_name}"
    ):
        (
            extracted_views,
            source_manifest,
        ) = (
            extract_sheet(
                sheet_path,

                source_root,

                white_threshold=(
                    args
                    .sheet_white_threshold
                ),

                alpha_threshold=(
                    args.threshold
                ),

                logger=(
                    logger.child()
                ),
            )
        )

        projections = (
            prepare_projections(
                extracted_views,
                logger=(
                    logger.child()
                ),
            )
        )

        material_views = (
            prepare_material_views(
                extracted_views,
                logger=(
                    logger.child()
                ),
            )
        )

        scanner = (
            NativeScanner()
        )

        scan_result = (
            scanner.scan_levels(
                projections,

                resolution=(
                    args.resolution
                ),

                levels=(
                    args.profiles
                ),

                symmetry_x=(
                    args.symmetry_x
                ),

                thread_count=(
                    args.thread_count
                ),

                build_meshes=True,

                voxel_size=(
                    args.voxel_size
                ),

                center_xy=True,

                mesh_mode=(
                    args.mesh_mode
                ),
            )
        )

        write_json(
            (
                sheet_root
                / "source.json"
            ),
            {
                "sheet": (
                    sheet_name
                ),

                "source": str(
                    sheet_path
                ),

                "manifest": (
                    source_manifest
                ),

                "available_views": list(
                    scan_result
                    .available_views
                ),

                "profiles": list(
                    scan_result
                    .requested_levels
                ),
            },
        )

        all_variants: list[
            BenchmarkVariant
        ] = []

        matrix_cells: dict[
            tuple[
                str,
                str,
            ],
            Path,
        ] = {}

        for profile in (
            args.profiles
        ):
            snapshot = (
                scan_result
                .snapshots
                .get(
                    profile
                )
            )

            if snapshot is None:
                raise RuntimeError(
                    (
                        "Native scan did not "
                        f"produce {profile}."
                    )
                )

            if snapshot.mesh is None:
                raise RuntimeError(
                    (
                        f"{profile} produced "
                        "no native mesh."
                    )
                )

            active_views = (
                material_views_for_snapshot(
                    material_views,

                    list(
                        snapshot
                        .applied_views
                    ),
                )
            )

            if not active_views:
                raise RuntimeError(
                    (
                        f"{profile} has no "
                        "material views."
                    )
                )

            source = (
                build_projection_source(
                    runtime,

                    extracted_views=(
                        extracted_views
                    ),

                    projections=(
                        projections
                    ),

                    material_views=(
                        material_views
                    ),

                    applied_views=(
                        snapshot
                        .applied_views
                    ),

                    alpha_threshold=(
                        args.threshold
                    ),
                )
            )

            (
                baseline,
                uv_variants,
            ) = (
                benchmark_profile(
                    runtime,

                    sheet_name=(
                        sheet_name
                    ),

                    profile=(
                        profile
                    ),

                    snapshot=(
                        snapshot
                    ),

                    source=(
                        source
                    ),

                    sheet_root=(
                        sheet_root
                    ),

                    args=(
                        args
                    ),

                    logger=(
                        logger.child()
                    ),
                )
            )

            all_variants.append(
                baseline
            )

            all_variants.extend(
                uv_variants
            )

            matrix_cells[
                (
                    profile,
                    "projected",
                )
            ] = (
                baseline
                .contact_sheet_path
            )

            for variant in (
                uv_variants
            ):
                matrix_cells[
                    (
                        profile,
                        f"uv-{variant.texture_size}",
                    )
                ] = (
                    variant
                    .contact_sheet_path
                )

        return (
            all_variants,
            matrix_cells,
        )


# =========================================================
# Console output
# =========================================================

def print_results(
    rows: list[
        dict[str, Any]
    ],
) -> None:
    print()

    print(
        "=" * 118
    )

    print(
        "UV BAKE RESOLUTION BENCHMARK"
    )

    print(
        "=" * 118
    )

    print(
        (
            "PROFILE | VARIANT              | BAKE    | "
            "COVERAGE | SUBPIXEL | GLB MiB | "
            "RGB MAE | PSNR"
        )
    )

    print(
        "-" * 118
    )

    for row in rows:
        if (
            row[
                "implementation"
            ]
            == PROJECTED_IMPLEMENTATION_ID
        ):
            label = (
                "Projected V1.2"
            )

        else:
            label = (
                f"UV {row['texture_size']}²"
            )

        print(
            (
                f"{row['profile']:>7} | "
                f"{label:<20} | "
                f"{float(row['material_seconds']):>6.2f}s | "
                f"{_percent(row['coverage_ratio']):>8} | "
                f"{_percent(row['subpixel_triangle_ratio']):>8} | "
                f"{_mib(row['glb_bytes']):>7} | "
                f"{_float_value(row['rgb_mae_vs_projected'], 5):>7} | "
                f"{_float_value(row['psnr_vs_projected'], 2):>6}"
            )
        )

    print(
        "=" * 118
    )


# =========================================================
# Main
# =========================================================

def main() -> None:
    args = (
        parse_args()
    )

    validate_args(
        args
    )

    example_dir = (
        args
        .example_dir
        .resolve()
    )

    output_root = (
        args
        .output
        .resolve()
    )

    # Benchmark output is disposable and must never contain
    # stale data from a previous resolution run.
    if output_root.exists():
        shutil.rmtree(
            output_root
        )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    sheets = (
        discover_sheets(
            example_dir,
            args.sheets,
        )
    )

    runtime = (
        load_pipeline_runtime()
    )

    logger = (
        RunLogger()
    )

    started_at = (
        time.perf_counter()
    )

    all_rows: list[
        dict[str, Any]
    ] = []

    failures = []

    global_matrix_cells = {}

    for sheet_path in sheets:
        try:
            (
                variants,
                sheet_cells,
            ) = (
                benchmark_sheet(
                    runtime,

                    sheet_path=(
                        sheet_path
                    ),

                    output_root=(
                        output_root
                    ),

                    args=(
                        args
                    ),

                    logger=(
                        logger
                    ),
                )
            )

            rows = [
                benchmark_row(
                    variant
                )
                for variant
                in variants
            ]

            all_rows.extend(
                rows
            )

            # -------------------------------------------------
            # For the initial benchmark we expect one sheet.
            #
            # If several sheets are requested, each sheet gets
            # its own visual matrix.
            # -------------------------------------------------

            columns = [
                "projected",
                *[
                    f"uv-{size}"
                    for size
                    in args
                    .texture_sizes
                ],
            ]

            sheet_matrix = (
                output_root
                / sheet_path.stem
                / "benchmark_matrix.png"
            )

            compose_matrix(
                sheet_cells,

                profiles=(
                    args.profiles
                ),

                columns=(
                    columns
                ),

                output_path=(
                    sheet_matrix
                ),

                gutter=(
                    args.gutter
                ),
            )

            if len(
                sheets
            ) == 1:
                shutil.copyfile(
                    sheet_matrix,

                    output_root
                    / "benchmark_matrix.png",
                )

            global_matrix_cells[
                sheet_path.stem
            ] = str(
                sheet_matrix
            )

        except Exception as exc:
            failures.append(
                {
                    "sheet": (
                        sheet_path.stem
                    ),

                    "type": (
                        type(
                            exc
                        ).__name__
                    ),

                    "error": str(
                        exc
                    ),
                }
            )

            if not (
                args
                .continue_on_error
            ):
                raise

    if not all_rows:
        raise RuntimeError(
            (
                "Benchmark produced "
                "no result rows."
            )
        )

    recommendation = (
        recommend_resolution(
            all_rows,

            profiles=(
                args.profiles
            ),

            texture_sizes=(
                args.texture_sizes
            ),

            max_subpixel_ratio=(
                args
                .max_subpixel_ratio
            ),
        )
    )

    elapsed = (
        time.perf_counter()
        - started_at
    )

    manifest = {
        "success": (
            len(
                failures
            )
            == 0
        ),

        "example_dir": str(
            example_dir
        ),

        "output": str(
            output_root
        ),

        "geometry": {
            "resolution": (
                args.resolution
            ),

            "mesh_mode": (
                args.mesh_mode
            ),

            "voxel_size": (
                args.voxel_size
            ),

            "target_height": (
                args.target_height
            ),
        },

        "benchmark": {
            "profiles": (
                args.profiles
            ),

            "texture_sizes": (
                args.texture_sizes
            ),

            "padding_pixels": (
                args.padding
            ),

            "samples_per_axis": (
                args
                .samples_per_axis
            ),

            "render_size": (
                args.render_size
            ),

            "views": (
                args.views
            ),

            "render_samples": (
                args.render_samples
            ),

            "max_subpixel_ratio": (
                args
                .max_subpixel_ratio
            ),
        },

        "rows": (
            all_rows
        ),

        "recommendation": (
            recommendation
        ),

        "matrices": (
            global_matrix_cells
        ),

        "failures": (
            failures
        ),

        "elapsed_seconds": (
            elapsed
        ),
    }

    write_json(
        (
            output_root
            / "benchmark.json"
        ),
        manifest,
    )

    markdown_path = (
        write_markdown(
            output_root,

            rows=(
                all_rows
            ),

            profiles=(
                args.profiles
            ),

            texture_sizes=(
                args.texture_sizes
            ),

            recommendation=(
                recommendation
            ),
        )
    )

    print_results(
        all_rows
    )

    print()

    print(
        (
            "Technical candidate: "
            f"{recommendation['texture_size']}²"
        )
    )

    print(
        (
            "Target met: "
            f"{recommendation['target_met']}"
        )
    )

    print(
        (
            "Benchmark JSON: "
            f"{output_root / 'benchmark.json'}"
        )
    )

    print(
        (
            "Benchmark Markdown: "
            f"{markdown_path}"
        )
    )

    print(
        (
            "Elapsed: "
            f"{elapsed:.2f}s"
        )
    )

    if failures:
        raise SystemExit(
            1
        )


if __name__ == "__main__":
    main()