from __future__ import annotations

import argparse
import hashlib
import json
import sys

from array import array
from dataclasses import dataclass
from pathlib import Path

import bpy

from mathutils import Matrix


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


from core.image_mask import BinaryMask
from core.native_bridge import NativeProjection
from core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)
from core.native_scan import NativeScanner
from core.presheet_layout import (
    CELL_SPECS,
    pixel_bbox,
)
from scripts.run_logger import RunLogger


# ---------------------------------------------------------
# Data
# ---------------------------------------------------------

@dataclass(frozen=True)
class ExtractedView:
    name: str
    path: Path

    azimuth_degrees: float
    elevation_degrees: float

    bbox: tuple[
        int,
        int,
        int,
        int,
    ]

    sha256: str

    valid: bool

    mask: BinaryMask


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def parse_args() -> argparse.Namespace:
    argv = sys.argv

    if "--" in argv:
        argv = argv[
            argv.index("--") + 1:
        ]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Generate Projection Tool "
            "examples using the native "
            "C++ engine."
        )
    )

    parser.add_argument(
        "example_dir",
        type=Path,
    )

    parser.add_argument(
        "output_dir",
        type=Path,
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=64,
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
    )

    parser.add_argument(
        "--sheet-white-threshold",
        type=float,
        default=0.94,
    )

    parser.add_argument(
        "--profiles",
        nargs="*",
        default=None,
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
        default=1.0,
    )

    parser.add_argument(
        "--target-height",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--json-log",
        action="store_true",
    )

    parser.add_argument(
        "--skip-blend",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )


# ---------------------------------------------------------
# Hashing
# ---------------------------------------------------------

def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


# ---------------------------------------------------------
# Connected component
# ---------------------------------------------------------

def _largest_component(
    foreground: bytearray,
    width: int,
    height: int,
) -> list[int]:
    """
    Return indices belonging to the largest
    4-connected foreground component.

    Uses bytearray + list rather than Python
    sets to avoid large per-pixel objects.
    """

    pixel_count = (
        width
        * height
    )

    visited = bytearray(
        pixel_count
    )

    largest: list[int] = []

    for start in range(
        pixel_count
    ):
        if (
            visited[start]
            or not foreground[start]
        ):
            continue

        visited[start] = 1

        stack = [
            start
        ]

        component: list[int] = []

        while stack:
            index = (
                stack.pop()
            )

            component.append(
                index
            )

            x = (
                index
                % width
            )

            if x > 0:
                neighbor = (
                    index
                    - 1
                )

                if (
                    foreground[
                        neighbor
                    ]
                    and not visited[
                        neighbor
                    ]
                ):
                    visited[
                        neighbor
                    ] = 1

                    stack.append(
                        neighbor
                    )

            if (
                x + 1
                < width
            ):
                neighbor = (
                    index
                    + 1
                )

                if (
                    foreground[
                        neighbor
                    ]
                    and not visited[
                        neighbor
                    ]
                ):
                    visited[
                        neighbor
                    ] = 1

                    stack.append(
                        neighbor
                    )

            if index >= width:
                neighbor = (
                    index
                    - width
                )

                if (
                    foreground[
                        neighbor
                    ]
                    and not visited[
                        neighbor
                    ]
                ):
                    visited[
                        neighbor
                    ] = 1

                    stack.append(
                        neighbor
                    )

            neighbor = (
                index
                + width
            )

            if (
                neighbor
                < pixel_count
                and foreground[
                    neighbor
                ]
                and not visited[
                    neighbor
                ]
            ):
                visited[
                    neighbor
                ] = 1

                stack.append(
                    neighbor
                )

        if (
            len(component)
            > len(largest)
        ):
            largest = (
                component
            )

    return largest


# ---------------------------------------------------------
# Cell extraction
# ---------------------------------------------------------

def _copy_cell_pixels(
    sheet_pixels: array,
    sheet_width: int,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
) -> tuple[
    array,
    int,
    int,
]:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    width = (
        x1
        - x0
    )

    height = (
        y1
        - y0
    )

    rgba = array(
        "f",
        [0.0],
    ) * (
        width
        * height
        * 4
    )

    row_float_count = (
        width
        * 4
    )

    for local_y in range(
        height
    ):
        source_pixel = (
            (
                y0
                + local_y
            )
            * sheet_width
            + x0
        )

        source_start = (
            source_pixel
            * 4
        )

        source_end = (
            source_start
            + row_float_count
        )

        target_start = (
            local_y
            * row_float_count
        )

        target_end = (
            target_start
            + row_float_count
        )

        rgba[
            target_start:
            target_end
        ] = sheet_pixels[
            source_start:
            source_end
        ]

    return (
        rgba,
        width,
        height,
    )


def _foreground_from_rgba(
    rgba: array,
    width: int,
    height: int,
    *,
    white_threshold: float,
) -> bytearray:
    pixel_count = (
        width
        * height
    )

    foreground = bytearray(
        pixel_count
    )

    source_index = 0

    for pixel_index in range(
        pixel_count
    ):
        red = rgba[
            source_index
        ]

        green = rgba[
            source_index + 1
        ]

        blue = rgba[
            source_index + 2
        ]

        alpha = rgba[
            source_index + 3
        ]

        foreground[
            pixel_index
        ] = (
            1
            if (
                alpha > 0.01
                and not (
                    red
                    >= white_threshold
                    and green
                    >= white_threshold
                    and blue
                    >= white_threshold
                )
            )
            else 0
        )

        source_index += 4

    return foreground


def _apply_component_alpha(
    rgba: array,
    width: int,
    height: int,
    component: list[int],
    *,
    valid: bool,
) -> bytearray:
    pixel_count = (
        width
        * height
    )

    keep = bytearray(
        pixel_count
    )

    if valid:
        for index in component:
            keep[index] = 1

    for pixel_index in range(
        pixel_count
    ):
        if keep[
            pixel_index
        ]:
            continue

        rgba[
            pixel_index
            * 4
            + 3
        ] = 0.0

    return keep


def _mask_from_component(
    rgba: array,
    keep: bytearray,
    width: int,
    height: int,
    *,
    alpha_threshold: float,
) -> BinaryMask:
    pixel_count = (
        width
        * height
    )

    values = bytearray(
        pixel_count
    )

    alpha_index = 3

    for pixel_index in range(
        pixel_count
    ):
        if (
            keep[pixel_index]
            and rgba[
                alpha_index
            ]
            >= alpha_threshold
        ):
            values[
                pixel_index
            ] = 1

        alpha_index += 4

    return BinaryMask(
        width=width,
        height=height,
        values=bytes(
            values
        ),
    )


def _save_extracted_png(
    rgba: array,
    width: int,
    height: int,
    output_path: Path,
) -> None:
    image = bpy.data.images.new(
        name=(
            "BPT_"
            + output_path.stem
        ),
        width=width,
        height=height,
        alpha=True,
    )

    try:
        image.pixels.foreach_set(
            rgba
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


def extract_cell(
    sheet_pixels: array,
    sheet_width: int,
    output_path: Path,
    *,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    white_threshold: float,
    alpha_threshold: float,
) -> tuple[
    bool,
    BinaryMask,
]:
    (
        rgba,
        width,
        height,
    ) = _copy_cell_pixels(
        sheet_pixels,
        sheet_width,
        bbox,
    )

    foreground = (
        _foreground_from_rgba(
            rgba,
            width,
            height,
            white_threshold=(
                white_threshold
            ),
        )
    )

    component = (
        _largest_component(
            foreground,
            width,
            height,
        )
    )

    minimum_component = max(
        64,
        int(
            width
            * height
            * 0.005
        ),
    )

    valid = (
        len(component)
        >= minimum_component
    )

    keep = (
        _apply_component_alpha(
            rgba,
            width,
            height,
            component,
            valid=valid,
        )
    )

    mask = (
        _mask_from_component(
            rgba,
            keep,
            width,
            height,
            alpha_threshold=(
                alpha_threshold
            ),
        )
    )

    _save_extracted_png(
        rgba,
        width,
        height,
        output_path,
    )

    return (
        valid,
        mask,
    )


# ---------------------------------------------------------
# Sheet extraction
# ---------------------------------------------------------

def extract_sheet(
    sheet_path: Path,
    output_dir: Path,
    *,
    white_threshold: float,
    alpha_threshold: float,
    logger: RunLogger,
) -> tuple[
    list[ExtractedView],
    dict,
]:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    sheet = bpy.data.images.load(
        str(
            sheet_path.resolve()
        ),
        check_existing=False,
    )

    sheet.update()

    width = int(
        sheet.size[0]
    )

    height = int(
        sheet.size[1]
    )

    if (
        width <= 0
        or height <= 0
    ):
        bpy.data.images.remove(
            sheet
        )

        raise ValueError(
            (
                f"Invalid sheet size: "
                f"{width}x{height}"
            )
        )

    # Read Blender RNA pixels once.
    #
    # Direct repeated access through
    # image.pixels[index] is significantly
    # slower than foreach_get().

    sheet_pixels = array(
        "f",
        [0.0],
    ) * (
        width
        * height
        * 4
    )

    sheet.pixels.foreach_get(
        sheet_pixels
    )

    views: list[
        ExtractedView
    ] = []

    try:
        for (
            index,
            (
                name,
                column,
                row,
                azimuth,
                elevation,
            ),
        ) in enumerate(
            CELL_SPECS,
            start=1,
        ):
            logger.progress(
                index,
                len(
                    CELL_SPECS
                ),
                f"extract {name}",
            )

            bbox = pixel_bbox(
                width,
                height,
                column,
                row,
            )

            output_path = (
                output_dir
                / f"{name}.png"
            )

            (
                valid,
                mask,
            ) = extract_cell(
                sheet_pixels,
                width,
                output_path,
                bbox=bbox,
                white_threshold=(
                    white_threshold
                ),
                alpha_threshold=(
                    alpha_threshold
                ),
            )

            views.append(
                ExtractedView(
                    name=name,
                    path=output_path,
                    azimuth_degrees=(
                        azimuth
                    ),
                    elevation_degrees=(
                        elevation
                    ),
                    bbox=bbox,
                    sha256=sha256_file(
                        output_path
                    ),
                    valid=valid,
                    mask=mask,
                )
            )

    finally:
        bpy.data.images.remove(
            sheet
        )

    manifest = {
        "engine": "native-cpp",
        "source": str(
            sheet_path
        ),
        "source_sha256": (
            sha256_file(
                sheet_path
            )
        ),
        "sheet_width": width,
        "sheet_height": height,
        "cuts": [
            {
                "view": view.name,
                "azimuth": (
                    view.azimuth_degrees
                ),
                "elevation": (
                    view.elevation_degrees
                ),
                "bbox": list(
                    view.bbox
                ),
                "output": (
                    view.path.name
                ),
                "sha256": (
                    view.sha256
                ),
                "valid": (
                    view.valid
                ),
                "mask_pixels": (
                    view.mask.occupied_count
                ),
            }
            for view
            in views
        ],
    }

    return (
        views,
        manifest,
    )


# ---------------------------------------------------------
# Native projections
# ---------------------------------------------------------

def prepare_projections(
    views: list[
        ExtractedView
    ],
    *,
    logger: RunLogger,
) -> dict[
    str,
    NativeProjection,
]:
    valid_views = [
        view
        for view in views
        if (
            view.valid
            and view.mask.occupied_count > 0
        )
    ]

    projections: dict[
        str,
        NativeProjection,
    ] = {}

    for index, view in enumerate(
        valid_views,
        start=1,
    ):
        logger.progress(
            index,
            len(
                valid_views
            ),
            f"mask {view.name}",
        )

        projections[
            view.name
        ] = NativeProjection(
            mask=view.mask,
            azimuth_degrees=(
                view.azimuth_degrees
            ),
            elevation_degrees=(
                view.elevation_degrees
            ),
            flip_x=False,
        )

    return projections


# ---------------------------------------------------------
# Blender scene
# ---------------------------------------------------------

def clear_scene() -> None:
    for obj in tuple(
        bpy.data.objects
    ):
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )


def scale_object_to_height(
    obj: bpy.types.Object,
    target_height: float,
) -> None:
    if target_height <= 0.0:
        raise ValueError(
            (
                "Target height must be "
                "greater than zero."
            )
        )

    current_height = float(
        obj.dimensions.z
    )

    if current_height <= 0.0:
        return

    scale = (
        target_height
        / current_height
    )

    obj.data.transform(
        Matrix.Scale(
            scale,
            4,
        )
    )

    obj.data.update()


def _select_only(
    obj: bpy.types.Object,
) -> None:
    for selected in tuple(
        bpy.context.selected_objects
    ):
        selected.select_set(
            False
        )

    obj.select_set(
        True
    )

    bpy.context.view_layer.objects.active = (
        obj
    )


# ---------------------------------------------------------
# Export
# ---------------------------------------------------------

def export_object(
    obj: bpy.types.Object,
    *,
    output_dir: Path,
    stem: str,
    save_blend: bool,
) -> dict:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    glb_path = (
        output_dir
        / f"{stem}.glb"
    )

    blend_path = (
        output_dir
        / f"{stem}.blend"
    )

    _select_only(
        obj
    )

    bpy.ops.export_scene.gltf(
        filepath=str(
            glb_path.resolve()
        ),
        export_format="GLB",
        use_selection=True,
    )

    if save_blend:
        bpy.ops.wm.save_as_mainfile(
            filepath=str(
                blend_path.resolve()
            )
        )

    return {
        "glb": str(
            glb_path
        ),
        "blend": (
            str(
                blend_path
            )
            if save_blend
            else None
        ),
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
    }


# ---------------------------------------------------------
# Sheet pipeline
# ---------------------------------------------------------

def process_sheet(
    sheet_path: Path,
    generated_root: Path,
    args: argparse.Namespace,
    *,
    logger: RunLogger,
) -> None:
    sheet_name = (
        sheet_path.stem
    )

    sheet_root = (
        generated_root
        / sheet_name
    )

    extracted_dir = (
        sheet_root
        / "extracted"
    )

    scans_root = (
        sheet_root
        / "scans"
    )

    sheet_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    with logger.section(
        f"sheet {sheet_name}",
        source=str(
            sheet_path
        ),
    ):
        with logger.timed(
            "extract sheet"
        ):
            (
                views,
                manifest,
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

        with logger.timed(
            "prepare masks"
        ):
            projections = (
                prepare_projections(
                    views,
                    logger=(
                        logger.child()
                    ),
                )
            )

        logger.info(
            "native scan input",
            views=", ".join(
                projections.keys()
            ),
            resolution=(
                args.resolution
            ),
            threads=(
                args.thread_count
            ),
        )

        scanner = (
            NativeScanner()
        )

        with logger.timed(
            "native scan"
        ):
            result = (
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
                )
            )

        manifest[
            "requested_profiles"
        ] = list(
            result.requested_levels
        )

        manifest[
            "available_views"
        ] = list(
            result.available_views
        )

        manifest[
            "profiles"
        ] = {}

        for (
            level_name,
            snapshot,
        ) in (
            result.snapshots.items()
        ):
            level_logger = (
                logger.child()
            )

            with level_logger.section(
                level_name,
                occupied_voxels=(
                    snapshot
                    .volume
                    .occupied_count
                ),
            ):
                profile_info = {
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
                    "bounds": (
                        list(
                            snapshot
                            .volume
                            .bounds
                        )
                        if (
                            snapshot
                            .volume
                            .bounds
                        )
                        else None
                    ),
                }

                if (
                    snapshot.mesh
                    is None
                ):
                    manifest[
                        "profiles"
                    ][
                        level_name
                    ] = profile_info

                    continue

                clear_scene()

                with level_logger.timed(
                    "inject native mesh"
                ):
                    obj = (
                        create_blender_mesh_from_native(
                            snapshot.mesh,
                            mesh_name=(
                                f"BPT_"
                                f"{sheet_name}_"
                                f"{level_name}"
                            ),
                            object_name=(
                                f"BPT_"
                                f"{sheet_name}_"
                                f"{level_name}"
                            ),
                        )
                    )

                with level_logger.timed(
                    "scale object"
                ):
                    scale_object_to_height(
                        obj,
                        args.target_height,
                    )

                with level_logger.timed(
                    "shade smooth"
                ):
                    shade_smooth_native_object(
                        obj
                    )

                with level_logger.timed(
                    "export GLB"
                ):
                    export_info = (
                        export_object(
                            obj,
                            output_dir=(
                                scans_root
                                / level_name
                            ),
                            stem=(
                                f"{sheet_name}_"
                                f"{level_name}"
                            ),
                            save_blend=(
                                not args.skip_blend
                            ),
                        )
                    )

                profile_info.update(
                    {
                        "generated": True,
                        **export_info,
                    }
                )

                manifest[
                    "profiles"
                ][
                    level_name
                ] = profile_info

        manifest_path = (
            sheet_root
            / "manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        logger.success(
            "manifest written",
            path=str(
                manifest_path
            ),
        )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    args = parse_args()

    example_dir = (
        args
        .example_dir
        .resolve()
    )

    output_dir = (
        args
        .output_dir
        .resolve()
    )

    sheets_dir = (
        example_dir
        / "sheets"
    )

    if not sheets_dir.exists():
        raise FileNotFoundError(
            (
                "Missing sheets directory: "
                f"{sheets_dir}"
            )
        )

    sheets = sorted(
        sheets_dir.glob(
            "sheet*.png"
        )
    )

    if not sheets:
        raise RuntimeError(
            (
                "No sheet*.png found in "
                f"{sheets_dir}"
            )
        )

    generated_root = (
        output_dir
        / "generated"
    )

    generated_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    logger = RunLogger(
        jsonl_path=(
            generated_root
            / "native_run.jsonl"
            if args.json_log
            else None
        )
    )

    logger.divider(
        "NATIVE C++ EXAMPLE GENERATION"
    )

    for index, sheet_path in enumerate(
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

        process_sheet(
            sheet_path,
            generated_root,
            args,
            logger=(
                logger.child()
            ),
        )

    logger.success(
        "native generation finished",
        elapsed=(
            logger.total_elapsed()
        ),
    )


if __name__ == "__main__":
    main()