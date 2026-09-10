from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
import time

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping

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
from scripts.run_logger import (
    RunLogger,
)


# =========================================================
# Constants
# =========================================================

SUPPORTED_IMPLEMENTATIONS = (
    "projected-color-v1.2",
    "uv-bake-v2",
)

DEFAULT_EXAMPLE_DIR = (
    REPO_ROOT
    / "example"
    / "mascotte"
    / "test1"
)

DEFAULT_PROFILES = (
    "L2",
    "L4",
    "L8",
    "L10",
)

DEFAULT_RESOLUTION = 64

DEFAULT_TEXTURE_SIZE = 256

DEFAULT_PADDING_PIXELS = 4

DEFAULT_SAMPLES_PER_AXIS = 1

DEFAULT_MESH_MODE = (
    "surface_nets"
)

DEFAULT_TARGET_HEIGHT = 2.0

DEFAULT_ALPHA_THRESHOLD = 0.1

DEFAULT_SHEET_WHITE_THRESHOLD = 0.94

DEFAULT_VOXEL_SIZE = 1.0

DEFAULT_UV_LAYER_NAME = (
    "MeshvennCompareUV"
)

DEFAULT_ISLAND_MARGIN = 0.02

DEFAULT_ANGLE_LIMIT_DEGREES = 66.0


# =========================================================
# Runtime package
# =========================================================

@dataclass(frozen=True)
class PipelineRuntime:
    package_name: str

    contracts: ModuleType

    projection_images: ModuleType

    native_visual_hull: ModuleType

    projected_color: ModuleType

    uv_bake: ModuleType


def load_pipeline_runtime() -> PipelineRuntime:
    """
    Load the production pipeline modules through Meshvenn's
    real package namespace.

    Existing historical scripts import core/ directly because
    they predate the generic pipeline.

    implementations/ uses package-relative imports:

        ..core
        .native_visual_hull

    so this comparison runner loads those implementations
    through the repository package itself.

    No Blender add-on registration is required.
    """

    package_name = (
        REPO_ROOT.name
    )

    if not package_name.isidentifier():
        raise RuntimeError(
            (
                "Repository directory must be a valid "
                "Python package name to run material "
                "comparison. "
                f"Received: {package_name!r}"
            )
        )

    package_parent = str(
        REPO_ROOT.parent
    )

    if package_parent not in sys.path:
        sys.path.insert(
            0,
            package_parent,
        )

    # Import root package once so relative implementation
    # imports resolve exactly as they do in the Blender
    # extension.
    importlib.import_module(
        package_name
    )

    return PipelineRuntime(
        package_name=package_name,

        contracts=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "core.pipeline_contracts"
                )
            )
        ),

        projection_images=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.projection_images"
                )
            )
        ),

        native_visual_hull=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.native_visual_hull"
                )
            )
        ),

        projected_color=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.projected_color"
                )
            )
        ),

        uv_bake=(
            importlib.import_module(
                (
                    f"{package_name}."
                    "implementations.uv_bake"
                )
            )
        ),
    )


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
            "Generate identical Meshvenn geometry with "
            "multiple MATERIAL implementations for visual "
            "comparison."
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
        default=None,
        help=(
            "Comparison output directory. "
            "Defaults to <example-dir>/material-comparison."
        ),
    )

    parser.add_argument(
        "--sheets",
        nargs="*",
        default=None,
        help=(
            "Optional sheet names. "
            "Example: sheet1 sheet2. "
            "Default: every sheet*.png."
        ),
    )

    parser.add_argument(
        "--profiles",
        nargs="+",
        default=list(
            DEFAULT_PROFILES
        ),
        help=(
            "Native scan profiles. "
            "Example: L2 L4 L8 L10."
        ),
    )

    parser.add_argument(
        "--implementations",
        nargs="+",
        choices=(
            SUPPORTED_IMPLEMENTATIONS
        ),
        default=list(
            SUPPORTED_IMPLEMENTATIONS
        ),
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=DEFAULT_RESOLUTION,
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
        default=DEFAULT_VOXEL_SIZE,
    )

    parser.add_argument(
        "--target-height",
        type=float,
        default=DEFAULT_TARGET_HEIGHT,
    )

    # -----------------------------------------------------
    # UV Bake preview configuration
    #
    # 256 is intentionally much cheaper than the product
    # default of 1024. The comparison is diagnostic first.
    # -----------------------------------------------------

    parser.add_argument(
        "--texture-size",
        type=int,
        choices=(
            64,
            128,
            256,
            512,
            1024,
            2048,
            4096,
        ),
        default=DEFAULT_TEXTURE_SIZE,
    )

    parser.add_argument(
        "--padding",
        type=int,
        default=DEFAULT_PADDING_PIXELS,
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
        default=DEFAULT_UV_LAYER_NAME,
    )

    parser.add_argument(
        "--island-margin",
        type=float,
        default=DEFAULT_ISLAND_MARGIN,
    )

    parser.add_argument(
        "--angle-limit",
        type=float,
        default=(
            DEFAULT_ANGLE_LIMIT_DEGREES
        ),
    )

    parser.add_argument(
        "--save-blend",
        action="store_true",
        help=(
            "Also save one .blend file per "
            "implementation/profile."
        ),
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    parser.add_argument(
        "--json-log",
        action="store_true",
    )

    return parser.parse_args(
        _script_arguments()
    )


# =========================================================
# Validation
# =========================================================

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
                "Resolution must be "
                "between 8 and 256."
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

    if args.thread_count < 0:
        raise ValueError(
            "Thread count cannot be negative."
        )

    if args.voxel_size <= 0.0:
        raise ValueError(
            "Voxel size must be positive."
        )

    if args.target_height <= 0.0:
        raise ValueError(
            "Target height must be positive."
        )

    if not (
        0
        <= args.padding
        <= 128
    ):
        raise ValueError(
            (
                "UV padding must be "
                "between 0 and 128."
            )
        )

    if not (
        0.0
        <= args.island_margin
        <= 1.0
    ):
        raise ValueError(
            (
                "UV island margin must "
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
                "Smart UV angle limit must "
                "be inside ]0, 90]."
            )
        )

    if (
        not args.uv_layer_name
        or not args.uv_layer_name.strip()
    ):
        raise ValueError(
            "UV layer name cannot be empty."
        )

    normalized_profiles = []

    for profile in args.profiles:
        normalized = (
            str(profile)
            .strip()
            .upper()
        )

        if not normalized:
            continue

        if normalized not in {
            "L2",
            "L4",
            "L8",
            "L10",
        }:
            raise ValueError(
                (
                    "Unsupported profile: "
                    f"{normalized}"
                )
            )

        if normalized not in normalized_profiles:
            normalized_profiles.append(
                normalized
            )

    if not normalized_profiles:
        raise ValueError(
            "At least one profile is required."
        )

    args.profiles = (
        normalized_profiles
    )


# =========================================================
# Discovery
# =========================================================

def discover_sheets(
    example_dir: Path,
    requested: list[str] | None,
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

    available = sorted(
        sheets_dir.glob(
            "sheet*.png"
        )
    )

    if not available:
        raise RuntimeError(
            (
                "No sheet*.png found in "
                f"{sheets_dir}"
            )
        )

    if not requested:
        return available

    wanted = {
        (
            Path(name).stem
            .strip()
            .lower()
        )
        for name
        in requested
        if str(name).strip()
    }

    selected = [
        path
        for path
        in available
        if (
            path.stem.lower()
            in wanted
        )
    ]

    discovered_names = {
        path.stem.lower()
        for path
        in selected
    }

    missing = sorted(
        wanted
        - discovered_names
    )

    if missing:
        raise ValueError(
            (
                "Requested sheets not found: "
                + ", ".join(
                    missing
                )
            )
        )

    return selected


# =========================================================
# JSON
# =========================================================

def json_safe(
    value: Any,
) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        Path,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): json_safe(
                item
            )
            for (
                key,
                item,
            )
            in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            json_safe(
                item
            )
            for item
            in value
        ]

    return str(
        value
    )


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
            json_safe(
                value
            ),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# =========================================================
# Pipeline source adapter
# =========================================================

def build_projection_source(
    runtime: PipelineRuntime,
    *,
    extracted_views,
    projections: dict,
    material_views: dict,
    applied_views,
    alpha_threshold: float,
):
    """
    Build the real ProjectionImagesOutput contract expected
    downstream by NativeVisualHullOutput.

    The extraction/native scan still comes from the existing
    diagnostic script, but MATERIAL receives the same
    contract as the product pipeline.
    """

    extracted_by_name = {
        view.name: view
        for view
        in extracted_views
    }

    prepared = []

    for view_name in applied_views:
        extracted = (
            extracted_by_name.get(
                view_name
            )
        )

        native_projection = (
            projections.get(
                view_name
            )
        )

        material_view = (
            material_views.get(
                view_name
            )
        )

        if extracted is None:
            raise RuntimeError(
                (
                    "Missing extracted view: "
                    f"{view_name}"
                )
            )

        if native_projection is None:
            raise RuntimeError(
                (
                    "Missing NativeProjection: "
                    f"{view_name}"
                )
            )

        if material_view is None:
            raise RuntimeError(
                (
                    "Missing ProjectedMaterialView: "
                    f"{view_name}"
                )
            )

        prepared.append(
            runtime
            .projection_images
            .PreparedProjectionView(
                name=(
                    extracted.name
                ),
                image_name=(
                    extracted.path.name
                ),
                width=(
                    extracted.mask.width
                ),
                height=(
                    extracted.mask.height
                ),
                azimuth_degrees=(
                    extracted
                    .azimuth_degrees
                ),
                elevation_degrees=(
                    extracted
                    .elevation_degrees
                ),
                flip_x=False,
                weight=1.0,
                mask=(
                    extracted.mask
                ),
                native_projection=(
                    native_projection
                ),
                material_view=(
                    material_view
                ),
            )
        )

    if not prepared:
        raise RuntimeError(
            (
                "No prepared views remain "
                "for this profile."
            )
        )

    return (
        runtime
        .projection_images
        .ProjectionImagesOutput(
            views=tuple(
                prepared
            ),
            alpha_threshold=float(
                alpha_threshold
            ),
            enabled_projection_count=len(
                prepared
            ),
            missing_image_count=0,
        )
    )


# =========================================================
# Geometry adapter
# =========================================================

def build_geometry_output(
    runtime: PipelineRuntime,
    *,
    obj: bpy.types.Object,
    snapshot,
    source,
    args: argparse.Namespace,
):
    """
    Represent the exact same native snapshot through the
    production NativeVisualHullOutput contract.

    We intentionally bake MATERIAL before target-height
    normalization, matching the real pipeline coordinate
    convention.
    """

    return (
        runtime
        .native_visual_hull
        .NativeVisualHullOutput(
            blender_object=obj,

            volume=(
                snapshot.volume
            ),

            native_mesh=(
                snapshot.mesh
            ),

            source=source,

            resolution=int(
                args.resolution
            ),

            symmetry_x=bool(
                args.symmetry_x
            ),

            thread_count=int(
                args.thread_count
            ),

            mesh_mode=str(
                args.mesh_mode
            ),

            voxel_size=float(
                args.voxel_size
            ),

            center_xy=True,

            normalized_height=False,

            target_height=None,

            normalization_scale=1.0,
        )
    )


# =========================================================
# Material configuration
# =========================================================

def build_material_settings(
    args: argparse.Namespace,
):
    """
    Lightweight settings object consumed by both production
    MATERIAL implementations.

    Shared V1.2 projection configuration is kept identical
    between both variants.
    """

    return SimpleNamespace(
        # -------------------------------------------------
        # Shared projected-color configuration
        # -------------------------------------------------

        material_enable_visibility=True,

        material_allow_backface_fallback=True,

        material_min_facing=0.10,

        material_facing_power=2.0,

        material_relative_score_cutoff=0.20,

        material_max_contributors=3,

        material_weight_power=1.5,

        # -------------------------------------------------
        # UV Bake
        # -------------------------------------------------

        uv_bake_texture_size=int(
            args.texture_size
        ),

        uv_bake_padding_pixels=int(
            args.padding
        ),

        uv_bake_samples_per_axis=int(
            args.samples_per_axis
        ),

        uv_bake_uv_layer_name=str(
            args.uv_layer_name
        ),

        uv_bake_island_margin=float(
            args.island_margin
        ),

        uv_bake_angle_limit_degrees=float(
            args.angle_limit
        ),

        # Force production Smart UV generation.
        uv_bake_reuse_existing_uv=False,
    )


# =========================================================
# Implementation
# =========================================================

def create_material_implementation(
    runtime: PipelineRuntime,
    implementation_id: str,
):
    if (
        implementation_id
        == "projected-color-v1.2"
    ):
        return (
            runtime
            .projected_color
            .ProjectedColorImplementation()
        )

    if (
        implementation_id
        == "uv-bake-v2"
    ):
        return (
            runtime
            .uv_bake
            .UVBakeImplementation()
        )

    raise ValueError(
        (
            "Unsupported MATERIAL implementation: "
            f"{implementation_id}"
        )
    )


def execute_material(
    runtime: PipelineRuntime,
    *,
    implementation_id: str,
    geometry,
    settings,
):
    PipelineContext = (
        runtime
        .contracts
        .PipelineContext
    )

    PipelineStage = (
        runtime
        .contracts
        .PipelineStage
    )

    context = PipelineContext(
        scene=(
            bpy.context.scene
        ),
        settings=settings,
    )

    context.set_output(
        PipelineStage.GEOMETRY,
        geometry,
    )

    implementation = (
        create_material_implementation(
            runtime,
            implementation_id,
        )
    )

    availability = (
        implementation
        .availability(
            context
        )
    )

    if not availability.available:
        raise RuntimeError(
            (
                f"{implementation_id} unavailable: "
                f"{availability.reason}. "
                f"{json_safe(availability.details)}"
            )
        )

    started_at = (
        time.perf_counter()
    )

    result = (
        implementation.execute(
            context
        )
    )

    elapsed = (
        time.perf_counter()
        - started_at
    )

    if not result.success:
        raise RuntimeError(
            (
                f"{implementation_id} failed: "
                f"{result.message}"
            )
        )

    return (
        result,
        elapsed,
        availability,
    )


# =========================================================
# Blender lifecycle
# =========================================================

def cleanup_object(
    obj: bpy.types.Object | None,
) -> None:
    if obj is None:
        return

    mesh = (
        obj.data
        if (
            obj.type == "MESH"
        )
        else None
    )

    materials = []

    images = []

    if mesh is not None:
        materials = [
            material
            for material
            in mesh.materials
            if material is not None
        ]

    for material in materials:
        node_tree = (
            material.node_tree
        )

        if node_tree is None:
            continue

        for node in (
            node_tree.nodes
        ):
            image = getattr(
                node,
                "image",
                None,
            )

            if (
                image is not None
                and image not in images
            ):
                images.append(
                    image
                )

    if (
        obj.name
        in bpy.data.objects
    ):
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )

    if (
        mesh is not None
        and mesh.users == 0
        and mesh.name
        in bpy.data.meshes
    ):
        bpy.data.meshes.remove(
            mesh
        )

    for material in materials:
        if (
            material.users == 0
            and material.name
            in bpy.data.materials
        ):
            bpy.data.materials.remove(
                material
            )

    for image in images:
        if (
            image.users == 0
            and image.name
            in bpy.data.images
        ):
            bpy.data.images.remove(
                image
            )


# =========================================================
# One variant
# =========================================================

def generate_variant(
    runtime: PipelineRuntime,
    *,
    implementation_id: str,
    sheet_name: str,
    level_name: str,
    snapshot,
    source,
    output_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> dict:
    clear_scene()

    obj = None

    try:
        object_name = (
            "MeshvennCompare_"
            f"{sheet_name}_"
            f"{level_name}_"
            f"{implementation_id}"
        )

        with logger.timed(
            "inject mesh"
        ):
            obj = (
                create_blender_mesh_from_native(
                    snapshot.mesh,
                    mesh_name=object_name,
                    object_name=object_name,
                )
            )

        with logger.timed(
            "shade smooth"
        ):
            shade_smooth_native_object(
                obj
            )

        geometry = (
            build_geometry_output(
                runtime,
                obj=obj,
                snapshot=snapshot,
                source=source,
                args=args,
            )
        )

        settings = (
            build_material_settings(
                args
            )
        )

        logger.info(
            "material implementation",
            implementation=(
                implementation_id
            ),
        )

        (
            material_result,
            material_elapsed,
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

        # -------------------------------------------------
        # Projection coordinates must remain native until
        # MATERIAL has completely finished.
        # -------------------------------------------------

        with logger.timed(
            "normalize height"
        ):
            scale_object_to_height(
                obj,
                args.target_height,
            )

        obj[
            "meshvenn_compare"
        ] = True

        obj[
            "meshvenn_compare_sheet"
        ] = sheet_name

        obj[
            "meshvenn_compare_profile"
        ] = level_name

        obj[
            "meshvenn_compare_material"
        ] = implementation_id

        variant_dir = (
            output_root
            / sheet_name
            / level_name
            / implementation_id
        )

        variant_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with logger.timed(
            "export GLB"
        ):
            export_info = (
                export_object(
                    obj,
                    output_dir=(
                        variant_dir
                    ),
                    stem="model",
                    save_blend=bool(
                        args.save_blend
                    ),
                )
            )

        payload = (
            material_result.payload
        )

        material_specific = {}

        # -------------------------------------------------
        # UV Bake diagnostics
        # -------------------------------------------------

        bake_result = getattr(
            payload,
            "bake_result",
            None,
        )

        if bake_result is not None:
            stats = (
                bake_result.stats
            )

            material_specific[
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
            }

        # -------------------------------------------------
        # Projected Color diagnostics
        # -------------------------------------------------

        projected_stats = getattr(
            payload,
            "stats",
            None,
        )

        if projected_stats is not None:
            material_specific[
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

        info = {
            "generated": True,

            "implementation": (
                implementation_id
            ),

            "availability": {
                "state": str(
                    availability.state.value
                ),
                "reason": (
                    availability.reason
                ),
                "details": json_safe(
                    availability.details
                ),
            },

            "material_seconds": (
                material_elapsed
            ),

            "result": {
                "message": (
                    material_result
                    .message
                ),
                "metrics": json_safe(
                    material_result
                    .metrics
                ),
                "metadata": json_safe(
                    material_result
                    .metadata
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
                    float(value)
                    for value
                    in obj.dimensions
                ],
                "mesh_mode": (
                    args.mesh_mode
                ),
                "occupied_voxels": (
                    snapshot
                    .volume
                    .occupied_count
                ),
            },

            **material_specific,

            "export": (
                export_info
            ),
        }

        write_json(
            (
                variant_dir
                / "variant.json"
            ),
            info,
        )

        logger.success(
            "variant generated",
            implementation=(
                implementation_id
            ),
            elapsed=(
                material_elapsed
            ),
            glb=(
                export_info[
                    "glb"
                ]
            ),
        )

        return info

    finally:
        cleanup_object(
            obj
        )


# =========================================================
# One sheet
# =========================================================

def process_sheet(
    runtime: PipelineRuntime,
    *,
    sheet_path: Path,
    output_root: Path,
    args: argparse.Namespace,
    logger: RunLogger,
) -> dict:
    sheet_name = (
        sheet_path.stem
    )

    sheet_output = (
        output_root
        / sheet_name
    )

    # Comparison output is disposable. Removing the previous
    # sheet avoids stale implementation/profile files.
    if sheet_output.exists():
        shutil.rmtree(
            sheet_output
        )

    sheet_output.mkdir(
        parents=True,
        exist_ok=True,
    )

    extracted_dir = (
        sheet_output
        / "source"
    )

    manifest = {
        "sheet": (
            sheet_name
        ),

        "source": str(
            sheet_path
        ),

        "resolution": (
            args.resolution
        ),

        "mesh_mode": (
            args.mesh_mode
        ),

        "profiles": {},

        "implementations": list(
            args.implementations
        ),

        "uv_bake_preview": {
            "texture_size": (
                args.texture_size
            ),
            "padding_pixels": (
                args.padding
            ),
            "samples_per_axis": (
                args.samples_per_axis
            ),
            "uv_layer_name": (
                args.uv_layer_name
            ),
            "island_margin": (
                args.island_margin
            ),
            "angle_limit_degrees": (
                args.angle_limit
            ),
        },
    }

    with logger.section(
        f"sheet {sheet_name}"
    ):
        # -------------------------------------------------
        # Extract source sheet.
        # -------------------------------------------------

        with logger.timed(
            "extract source views"
        ):
            (
                extracted_views,
                source_manifest,
            ) = extract_sheet(
                sheet_path,
                extracted_dir,
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

        manifest[
            "source_manifest"
        ] = (
            source_manifest
        )

        # -------------------------------------------------
        # Prepare geometry + material inputs once.
        # -------------------------------------------------

        with logger.timed(
            "prepare projections"
        ):
            projections = (
                prepare_projections(
                    extracted_views,
                    logger=(
                        logger.child()
                    ),
                )
            )

        with logger.timed(
            "prepare material views"
        ):
            material_views = (
                prepare_material_views(
                    extracted_views,
                    logger=(
                        logger.child()
                    ),
                )
            )

        # -------------------------------------------------
        # Geometry is reconstructed ONCE.
        #
        # Both MATERIAL implementations receive snapshots
        # from this exact same scan.
        # -------------------------------------------------

        scanner = (
            NativeScanner()
        )

        with logger.timed(
            "native scan"
        ):
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

        manifest[
            "available_views"
        ] = list(
            scan_result
            .available_views
        )

        manifest[
            "requested_profiles"
        ] = list(
            scan_result
            .requested_levels
        )

        # -------------------------------------------------
        # Compare MATERIAL implementations.
        # -------------------------------------------------

        for (
            level_name,
            snapshot,
        ) in (
            scan_result
            .snapshots
            .items()
        ):
            level_info = {
                "generated": False,

                "views": list(
                    snapshot
                    .applied_views
                ),

                "occupied_voxels": (
                    snapshot
                    .volume
                    .occupied_count
                ),

                "implementations": {},
            }

            manifest[
                "profiles"
            ][
                level_name
            ] = (
                level_info
            )

            if snapshot.mesh is None:
                level_info[
                    "reason"
                ] = (
                    "Native scan produced no mesh."
                )

                continue

            active_material_views = (
                material_views_for_snapshot(
                    material_views,
                    list(
                        snapshot
                        .applied_views
                    ),
                )
            )

            if not active_material_views:
                level_info[
                    "reason"
                ] = (
                    "No material views are "
                    "available for this profile."
                )

                continue

            source = (
                build_projection_source(
                    runtime,
                    extracted_views=(
                        extracted_views
                    ),
                    projections=projections,
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

            for implementation_id in (
                args.implementations
            ):
                variant_logger = (
                    logger.child()
                )

                try:
                    with (
                        variant_logger
                        .section(
                            (
                                f"{level_name} / "
                                f"{implementation_id}"
                            )
                        )
                    ):
                        info = (
                            generate_variant(
                                runtime,
                                implementation_id=(
                                    implementation_id
                                ),
                                sheet_name=(
                                    sheet_name
                                ),
                                level_name=(
                                    level_name
                                ),
                                snapshot=(
                                    snapshot
                                ),
                                source=source,
                                output_root=(
                                    output_root
                                ),
                                args=args,
                                logger=(
                                    variant_logger
                                ),
                            )
                        )

                    level_info[
                        "implementations"
                    ][
                        implementation_id
                    ] = info

                except Exception as exc:
                    level_info[
                        "implementations"
                    ][
                        implementation_id
                    ] = {
                        "generated": False,

                        "error": str(
                            exc
                        ),

                        "exception_type": (
                            type(exc).__name__
                        ),
                    }

                    variant_logger.error(
                        "variant failed",
                        implementation=(
                            implementation_id
                        ),
                        error=str(
                            exc
                        ),
                    )

                    if (
                        not args
                        .continue_on_error
                    ):
                        raise

            level_info[
                "generated"
            ] = any(
                bool(
                    implementation_info
                    .get(
                        "generated",
                        False,
                    )
                )
                for implementation_info
                in (
                    level_info[
                        "implementations"
                    ]
                    .values()
                )
            )

    manifest_path = (
        sheet_output
        / "comparison.json"
    )

    write_json(
        manifest_path,
        manifest,
    )

    logger.success(
        "sheet comparison written",
        path=str(
            manifest_path
        ),
    )

    return manifest


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
        args.example_dir
        .resolve()
    )

    if args.output is None:
        output_root = (
            example_dir
            / "material-comparison"
        )

    else:
        output_root = (
            args.output
            .resolve()
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

    logger = RunLogger(
        jsonl_path=(
            output_root
            / "material-comparison.jsonl"
            if args.json_log
            else None
        )
    )

    logger.divider(
        "MESHVENN MATERIAL COMPARISON"
    )

    logger.info(
        "Blender",
        version=(
            bpy.app.version_string
        ),
    )

    logger.info(
        "Example",
        path=str(
            example_dir
        ),
    )

    logger.info(
        "Output",
        path=str(
            output_root
        ),
    )

    logger.info(
        "Profiles",
        value=", ".join(
            args.profiles
        ),
    )

    logger.info(
        "Implementations",
        value=", ".join(
            args.implementations
        ),
    )

    logger.info(
        "Geometry",
        resolution=(
            args.resolution
        ),
        mesh_mode=(
            args.mesh_mode
        ),
    )

    logger.info(
        "UV Bake preview",
        texture_size=(
            args.texture_size
        ),
        padding=(
            args.padding
        ),
        samples_per_axis=(
            args.samples_per_axis
        ),
    )

    started_at = (
        time.perf_counter()
    )

    global_manifest = {
        "example": str(
            example_dir
        ),

        "output": str(
            output_root
        ),

        "profiles": list(
            args.profiles
        ),

        "implementations": list(
            args.implementations
        ),

        "resolution": (
            args.resolution
        ),

        "mesh_mode": (
            args.mesh_mode
        ),

        "texture_size": (
            args.texture_size
        ),

        "sheets": {},
    }

    failures = []

    for (
        index,
        sheet_path,
    ) in enumerate(
        sheets,
        start=1,
    ):
        logger.progress(
            index,
            len(
                sheets
            ),
            sheet_path.name,
        )

        try:
            sheet_manifest = (
                process_sheet(
                    runtime,
                    sheet_path=(
                        sheet_path
                    ),
                    output_root=(
                        output_root
                    ),
                    args=args,
                    logger=(
                        logger.child()
                    ),
                )
            )

            global_manifest[
                "sheets"
            ][
                sheet_path.stem
            ] = (
                sheet_manifest
            )

        except Exception as exc:
            failures.append(
                {
                    "sheet": (
                        sheet_path.stem
                    ),
                    "error": str(
                        exc
                    ),
                    "exception_type": (
                        type(exc).__name__
                    ),
                }
            )

            logger.error(
                "sheet failed",
                sheet=(
                    sheet_path.stem
                ),
                error=str(
                    exc
                ),
            )

            if (
                not args
                .continue_on_error
            ):
                raise

    elapsed = (
        time.perf_counter()
        - started_at
    )

    global_manifest[
        "elapsed_seconds"
    ] = elapsed

    global_manifest[
        "failures"
    ] = failures

    global_manifest[
        "success"
    ] = (
        len(
            failures
        )
        == 0
    )

    manifest_path = (
        output_root
        / "comparison.json"
    )

    write_json(
        manifest_path,
        global_manifest,
    )

    logger.divider(
        "MATERIAL COMPARISON SUMMARY"
    )

    logger.info(
        "Sheets",
        count=len(
            sheets
        ),
    )

    logger.info(
        "Failures",
        count=len(
            failures
        ),
    )

    logger.info(
        "Elapsed",
        seconds=elapsed,
    )

    logger.success(
        "comparison generation finished",
        manifest=str(
            manifest_path
        ),
    )

    if failures:
        raise SystemExit(
            1
        )


if __name__ == "__main__":
    main()