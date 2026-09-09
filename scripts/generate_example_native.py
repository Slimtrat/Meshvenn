from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import bpy

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.image_mask import rgba_to_mask
from core.native_bridge import NativeProjection
from core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)
from core.native_scan import NativeScanner
from scripts.run_logger import RunLogger


PRESHEET_V1_COLUMNS = (
    (0.016, 0.164),
    (0.169, 0.317),
    (0.324, 0.472),
    (0.478, 0.626),
    (0.632, 0.780),
)

PRESHEET_V1_ROWS = (
    (0.158, 0.432),
    (0.525, 0.801),
)

CELL_SPECS = (
    ("000", 0, 0, 0.0, 0.0),
    ("045", 1, 0, 45.0, 0.0),
    ("090", 2, 0, 90.0, 0.0),
    ("135", 3, 0, 135.0, 0.0),
    ("180", 4, 0, 180.0, 0.0),
    ("225", 0, 1, 225.0, 0.0),
    ("270", 1, 1, 270.0, 0.0),
    ("315", 2, 1, 315.0, 0.0),
    ("TOP", 3, 1, 0.0, 90.0),
    ("BOT", 4, 1, 0.0, -90.0),
)


@dataclass(frozen=True)
class ExtractedView:
    name: str
    path: Path
    azimuth_degrees: float
    elevation_degrees: float
    bbox: tuple[int, int, int, int]
    sha256: str
    valid: bool


def parse_args() -> argparse.Namespace:
    argv = sys.argv

    if "--" in argv:
        argv = argv[
            argv.index("--") + 1 :
        ]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Generate Projection Tool examples "
            "using the native C++ engine."
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


def _pixel_bbox(
    image_width: int,
    image_height: int,
    column: int,
    row: int,
) -> tuple[int, int, int, int]:
    x0n, x1n = (
        PRESHEET_V1_COLUMNS[
            column
        ]
    )

    topn, bottomn = (
        PRESHEET_V1_ROWS[
            row
        ]
    )

    x0 = round(
        x0n * image_width
    )

    x1 = round(
        x1n * image_width
    )

    y0 = round(
        (1.0 - bottomn)
        * image_height
    )

    y1 = round(
        (1.0 - topn)
        * image_height
    )

    return (
        x0,
        y0,
        x1,
        y1,
    )


def _largest_component(
    foreground: bytearray,
    width: int,
    height: int,
) -> set[int]:
    visited = bytearray(
        width * height
    )

    largest: set[int] = set()

    for start, value in enumerate(
        foreground
    ):
        if (
            visited[start]
            or not value
        ):
            continue

        visited[start] = 1

        stack = [
            start
        ]

        component: set[int] = set()

        while stack:
            index = stack.pop()

            component.add(
                index
            )

            x = (
                index
                % width
            )

            y = (
                index
                // width
            )

            if x > 0:
                neighbor = (
                    index - 1
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

            if x + 1 < width:
                neighbor = (
                    index + 1
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

            if y > 0:
                neighbor = (
                    index - width
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

            if y + 1 < height:
                neighbor = (
                    index + width
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
            len(component)
            > len(largest)
        ):
            largest = (
                component
            )

    return largest


def extract_cell(
    sheet: bpy.types.Image,
    output_path: Path,
    *,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    white_threshold: float,
) -> bool:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    width = (
        x1 - x0
    )

    height = (
        y1 - y0
    )

    sheet_width = int(
        sheet.size[0]
    )

    source = (
        sheet.pixels
    )

    rgba = [
        0.0
    ] * (
        width
        * height
        * 4
    )

    foreground = bytearray(
        width
        * height
    )

    for local_y in range(
        height
    ):
        source_y = (
            y0 + local_y
        )

        source_row = (
            source_y
            * sheet_width
        )

        for local_x in range(
            width
        ):
            source_x = (
                x0 + local_x
            )

            source_index = (
                source_row
                + source_x
            ) * 4

            pixel_index = (
                local_y
                * width
                + local_x
            )

            target_index = (
                pixel_index
                * 4
            )

            red = float(
                source[
                    source_index
                ]
            )

            green = float(
                source[
                    source_index
                    + 1
                ]
            )

            blue = float(
                source[
                    source_index
                    + 2
                ]
            )

            alpha = float(
                source[
                    source_index
                    + 3
                ]
            )

            rgba[
                target_index
            ] = red

            rgba[
                target_index + 1
            ] = green

            rgba[
                target_index + 2
            ] = blue

            rgba[
                target_index + 3
            ] = alpha

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

    if valid:
        keep = component

        for pixel_index in range(
            width * height
        ):
            if (
                pixel_index
                not in keep
            ):
                rgba[
                    pixel_index
                    * 4
                    + 3
                ] = 0.0

    else:
        for pixel_index in range(
            width * height
        ):
            rgba[
                pixel_index
                * 4
                + 3
            ] = 0.0

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

    return valid


def extract_sheet(
    sheet_path: Path,
    output_dir: Path,
    *,
    white_threshold: float,
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

            bbox = _pixel_bbox(
                width,
                height,
                column,
                row,
            )

            output_path = (
                output_dir
                / f"{name}.png"
            )

            valid = extract_cell(
                sheet,
                output_path,
                bbox=bbox,
                white_threshold=(
                    white_threshold
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
                    view
                    .azimuth_degrees
                ),
                "elevation": (
                    view
                    .elevation_degrees
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
            }
            for view in views
        ],
    }

    return (
        views,
        manifest,
    )


def image_to_native_projection(
    view: ExtractedView,
    *,
    threshold: float,
) -> NativeProjection:
    image = bpy.data.images.load(
        str(
            view.path.resolve()
        ),
        check_existing=False,
    )

    image.update()

    try:
        width = int(
            image.size[0]
        )

        height = int(
            image.size[1]
        )

        pixels = tuple(
            image.pixels[:]
        )

        mask = rgba_to_mask(
            pixels=pixels,
            width=width,
            height=height,
            alpha_threshold=(
                threshold
            ),
        )

    finally:
        bpy.data.images.remove(
            image
        )

    return NativeProjection(
        mask=mask,
        azimuth_degrees=(
            view
            .azimuth_degrees
        ),
        elevation_degrees=(
            view
            .elevation_degrees
        ),
        flip_x=False,
    )


def prepare_projections(
    views: list[
        ExtractedView
    ],
    *,
    threshold: float,
    logger: RunLogger,
) -> dict[
    str,
    NativeProjection,
]:
    valid_views = [
        view
        for view in views
        if view.valid
    ]

    result: dict[
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

        result[
            view.name
        ] = (
            image_to_native_projection(
                view,
                threshold=threshold,
            )
        )

    return result


def clear_scene() -> None:
    bpy.ops.object.select_all(
        action="SELECT"
    )

    bpy.ops.object.delete(
        use_global=False
    )


def scale_object_to_height(
    obj: bpy.types.Object,
    target_height: float,
) -> None:
    if target_height <= 0.0:
        raise ValueError(
            "Target height must be greater than zero."
        )

    height = float(
        obj.dimensions.z
    )

    if height <= 0.0:
        return

    scale = (
        target_height
        / height
    )

    obj.scale = (
        scale,
        scale,
        scale,
    )

    bpy.context.view_layer.objects.active = (
        obj
    )

    obj.select_set(
        True
    )

    bpy.ops.object.transform_apply(
        location=False,
        rotation=False,
        scale=True,
    )


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

    bpy.ops.object.select_all(
        action="DESELECT"
    )

    obj.select_set(
        True
    )

    bpy.context.view_layer.objects.active = (
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
            float(
                value
            )
            for value
            in obj.dimensions
        ],
    }


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
                logger=logger.child(),
            )

        with logger.timed(
            "prepare masks"
        ):
            projections = (
                prepare_projections(
                    views,
                    threshold=(
                        args.threshold
                    ),
                    logger=(
                        logger.child()
                    ),
                )
            )

        logger.info(
            "native scan input",
            views=", ".join(
                sorted(
                    projections
                    .keys()
                )
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
            result = scanner.scan_levels(
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

        manifest[
            "profiles"
        ] = {}

        for (
            level_name,
            snapshot,
        ) in result.snapshots.items():
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
                if (
                    snapshot.mesh
                    is None
                ):
                    continue

                clear_scene()

                with level_logger.timed(
                    "inject native mesh"
                ):
                    obj = (
                        create_blender_mesh_from_native(
                            snapshot.mesh,
                            mesh_name=(
                                f"BPT_{sheet_name}_{level_name}"
                            ),
                            object_name=(
                                f"BPT_{sheet_name}_{level_name}"
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
                                f"{sheet_name}_{level_name}"
                            ),
                            save_blend=(
                                not args.skip_blend
                            ),
                        )
                    )

                manifest[
                    "profiles"
                ][
                    level_name
                ] = {
                    "generated": True,
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
                        if snapshot
                        .volume
                        .bounds
                        else None
                    ),
                    **export_info,
                }

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
            f"Missing sheets directory: {sheets_dir}"
        )

    sheets = sorted(
        sheets_dir.glob(
            "sheet*.png"
        )
    )

    if not sheets:
        raise RuntimeError(
            f"No sheet*.png found in {sheets_dir}"
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
            len(sheets),
            sheet_path.name,
        )

        process_sheet(
            sheet_path,
            generated_root,
            args,
            logger=logger.child(),
        )

    logger.success(
        "native generation finished",
        elapsed=(
            logger.total_elapsed()
        ),
    )


if __name__ == "__main__":
    main()