from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import bpy

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.cleanup import cleanup_generated_object
from core.masks import rgba_to_mask
from core.mesh_builder import build_surface_mesh, scale_mesh_to_height
from core.visual_hull import (
    ProjectionView,
    VisualHullOptions,
    build_visual_hull,
    crop_empty_bounds,
)
from scripts.scan_profiles import available_profiles


# Presheet V1 geometry, normalized against the full template image.
# This matches the "Projection Tool - Fiche de prise de vues" template:
# 5 cells on the first row + 5 cells on the second row, with sidebar preserved.
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
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []

    parser = argparse.ArgumentParser(
        description="Generate all scan levels from sheet*.png files."
    )
    parser.add_argument("example_dir", type=Path)
    parser.add_argument("output_dir", type=Path)

    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--target-height", type=float, default=2.0)
    parser.add_argument("--voxel-size", type=float, default=0.05)
    parser.add_argument("--smooth", type=int, default=3)
    parser.add_argument("--symmetry-x", action="store_true")
    parser.add_argument("--no-remesh", action="store_true")

    parser.add_argument(
        "--sheet-white-threshold",
        type=float,
        default=0.94,
        help="RGB threshold used to turn near-white cell background transparent.",
    )

    parser.add_argument(
        "--profiles",
        nargs="*",
        default=None,
        help="Optional subset, e.g. --profiles L2 L4 L8",
    )

    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _pixel_bbox(
    image_width: int,
    image_height: int,
    column: int,
    row: int,
) -> tuple[int, int, int, int]:
    x0n, x1n = PRESHEET_V1_COLUMNS[column]
    topn, bottomn = PRESHEET_V1_ROWS[row]

    x0 = round(x0n * image_width)
    x1 = round(x1n * image_width)

    # Blender image pixels use bottom-left origin.
    y0 = round((1.0 - bottomn) * image_height)
    y1 = round((1.0 - topn) * image_height)

    return x0, y0, x1, y1


def _largest_component(
    foreground: list[bool],
    width: int,
    height: int,
) -> set[int]:
    visited = bytearray(width * height)
    largest: set[int] = set()

    for start in range(width * height):
        if visited[start] or not foreground[start]:
            continue

        visited[start] = 1
        stack = [start]
        component: set[int] = set()

        while stack:
            index = stack.pop()
            component.add(index)

            x = index % width
            y = index // width

            neighbors = []

            if x > 0:
                neighbors.append(index - 1)
            if x + 1 < width:
                neighbors.append(index + 1)
            if y > 0:
                neighbors.append(index - width)
            if y + 1 < height:
                neighbors.append(index + width)

            for neighbor in neighbors:
                if visited[neighbor] or not foreground[neighbor]:
                    continue

                visited[neighbor] = 1
                stack.append(neighbor)

        if len(component) > len(largest):
            largest = component

    return largest


def extract_cell(
    sheet: bpy.types.Image,
    output_path: Path,
    *,
    bbox: tuple[int, int, int, int],
    white_threshold: float,
) -> bool:
    x0, y0, x1, y1 = bbox

    width = x1 - x0
    height = y1 - y0

    source = sheet.pixels

    rgba = [0.0] * (width * height * 4)
    foreground = [False] * (width * height)

    for local_y in range(height):
        source_y = y0 + local_y

        for local_x in range(width):
            source_x = x0 + local_x

            source_index = (source_y * int(sheet.size[0]) + source_x) * 4
            pixel_index = local_y * width + local_x
            target_index = pixel_index * 4

            red = float(source[source_index])
            green = float(source[source_index + 1])
            blue = float(source[source_index + 2])
            alpha = float(source[source_index + 3])

            rgba[target_index] = red
            rgba[target_index + 1] = green
            rgba[target_index + 2] = blue
            rgba[target_index + 3] = alpha

            foreground[pixel_index] = (
                alpha > 0.01
                and not (
                    red >= white_threshold
                    and green >= white_threshold
                    and blue >= white_threshold
                )
            )

    component = _largest_component(foreground, width, height)

    # Reject nearly-empty cells.
    minimum_component = max(64, int(width * height * 0.005))
    valid = len(component) >= minimum_component

    if valid:
        for pixel_index in range(width * height):
            if pixel_index not in component:
                rgba[pixel_index * 4 + 3] = 0.0
    else:
        for pixel_index in range(width * height):
            rgba[pixel_index * 4 + 3] = 0.0

    extracted = bpy.data.images.new(
        name=f"BPT_{output_path.stem}",
        width=width,
        height=height,
        alpha=True,
    )

    try:
        extracted.pixels.foreach_set(rgba)
        extracted.filepath_raw = str(output_path.resolve())
        extracted.file_format = "PNG"
        extracted.save()
    finally:
        bpy.data.images.remove(extracted)

    return valid


def extract_presheet(
    sheet_path: Path,
    output_dir: Path,
    *,
    white_threshold: float,
) -> tuple[list[ExtractedView], dict]:
    output_dir.mkdir(parents=True, exist_ok=True)

    sheet = bpy.data.images.load(
        str(sheet_path.resolve()),
        check_existing=False,
    )
    sheet.update()

    image_width = int(sheet.size[0])
    image_height = int(sheet.size[1])

    extracted_views: list[ExtractedView] = []

    try:
        for name, column, row, azimuth, elevation in CELL_SPECS:
            bbox = _pixel_bbox(
                image_width,
                image_height,
                column,
                row,
            )

            output_path = output_dir / f"{name}.png"

            valid = extract_cell(
                sheet,
                output_path,
                bbox=bbox,
                white_threshold=white_threshold,
            )

            extracted_views.append(
                ExtractedView(
                    name=name,
                    path=output_path,
                    azimuth_degrees=azimuth,
                    elevation_degrees=elevation,
                    bbox=bbox,
                    sha256=sha256_file(output_path),
                    valid=valid,
                )
            )

            print(
                f"[projection-tool] cut {name}: "
                f"{'valid' if valid else 'empty'} bbox={bbox}"
            )
    finally:
        bpy.data.images.remove(sheet)

    manifest = {
        "source": str(sheet_path),
        "source_sha256": sha256_file(sheet_path),
        "sheet_width": image_width,
        "sheet_height": image_height,
        "template": {
            "id": "presheet_v1",
            "columns": 5,
            "rows": 2,
        },
        "cuts": [
            {
                "view": view.name,
                "azimuth": view.azimuth_degrees,
                "elevation": view.elevation_degrees,
                "bbox": list(view.bbox),
                "output": str(view.path.name),
                "sha256": view.sha256,
                "valid": view.valid,
            }
            for view in extracted_views
        ],
        "available_views": [
            view.name
            for view in extracted_views
            if view.valid
        ],
    }

    return extracted_views, manifest


def image_to_mask(path: Path, alpha_threshold: float):
    image = bpy.data.images.load(
        str(path.resolve()),
        check_existing=False,
    )
    image.update()

    width = int(image.size[0])
    height = int(image.size[1])

    try:
        return rgba_to_mask(
            pixels=tuple(image.pixels[:]),
            width=width,
            height=height,
            alpha_threshold=alpha_threshold,
        )
    finally:
        bpy.data.images.remove(image)


def build_projection(view: ExtractedView, threshold: float) -> ProjectionView:
    return ProjectionView(
        mask=image_to_mask(view.path, threshold),
        azimuth_degrees=view.azimuth_degrees,
        elevation_degrees=view.elevation_degrees,
        enabled=True,
    )


def clear_scene() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def create_object(vertices, faces) -> bpy.types.Object:
    mesh = bpy.data.meshes.new("ProjectionToolExampleMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    obj = bpy.data.objects.new("ProjectionToolExampleScan", mesh)
    bpy.context.scene.collection.objects.link(obj)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    return obj


def export_scan(
    obj: bpy.types.Object,
    scan_dir: Path,
    file_stem: str,
) -> dict:
    scan_dir.mkdir(parents=True, exist_ok=True)

    blend_path = scan_dir / f"{file_stem}.blend"
    glb_path = scan_dir / f"{file_stem}.glb"

    bpy.ops.wm.save_as_mainfile(
        filepath=str(blend_path.resolve())
    )

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.export_scene.gltf(
        filepath=str(glb_path.resolve()),
        export_format="GLB",
        use_selection=True,
    )

    dimensions = [float(value) for value in obj.dimensions]

    return {
        "blend": str(blend_path),
        "glb": str(glb_path),
        "vertices": len(obj.data.vertices),
        "faces": len(obj.data.polygons),
        "dimensions": dimensions,
    }


def generate_profile(
    profile,
    views_by_name: dict[str, ExtractedView],
    *,
    scan_dir: Path,
    file_stem: str,
    args: argparse.Namespace,
) -> dict:
    selected_views = [
        views_by_name[name]
        for name in profile.views
    ]

    clear_scene()

    projections = [
        build_projection(view, args.threshold)
        for view in selected_views
    ]

    volume = build_visual_hull(
        projections,
        options=VisualHullOptions(
            resolution=args.resolution,
            symmetry_x=args.symmetry_x,
        ),
    )

    if volume.occupied_count == 0:
        raise RuntimeError(
            f"{profile.name} produced an empty volume."
        )

    cropped = crop_empty_bounds(volume)

    mesh_data = build_surface_mesh(
        cropped,
        voxel_size=1.0,
        center=True,
    )

    mesh_data = scale_mesh_to_height(
        mesh_data,
        args.target_height,
    )

    obj = create_object(
        mesh_data.vertices,
        mesh_data.faces,
    )

    cleanup_generated_object(
        obj,
        auto_remesh=not args.no_remesh,
        voxel_size=args.voxel_size,
        smooth_iterations=args.smooth,
    )

    result = export_scan(
        obj,
        scan_dir,
        file_stem,
    )

    result.update(
        {
            "profile": profile.name,
            "views": list(profile.views),
            "resolution": args.resolution,
            "occupied_voxels": volume.occupied_count,
        }
    )

    return result


def process_sheet(
    sheet_path: Path,
    generated_root: Path,
    args: argparse.Namespace,
) -> None:
    sheet_name = sheet_path.stem
    sheet_root = generated_root / sheet_name
    extracted_dir = sheet_root / "extracted"
    scans_root = sheet_root / "scans"

    views, manifest = extract_presheet(
        sheet_path,
        extracted_dir,
        white_threshold=args.sheet_white_threshold,
    )

    valid_views = {
        view.name: view
        for view in views
        if view.valid
    }

    profiles = available_profiles(set(valid_views))

    if args.profiles:
        requested = {name.upper() for name in args.profiles}
        profiles = [
            profile
            for profile in profiles
            if profile.name in requested
        ]

    manifest["profiles"] = {}

    for profile in profiles:
        print(
            f"[projection-tool] {sheet_name} -> {profile.name}: "
            f"{', '.join(profile.views)}"
        )

        profile_dir = scans_root / profile.name

        try:
            result = generate_profile(
                profile,
                valid_views,
                scan_dir=profile_dir,
                file_stem=f"{sheet_name}_{profile.name}",
                args=args,
            )

            manifest["profiles"][profile.name] = {
                "generated": True,
                **result,
            }
        except Exception as exc:
            manifest["profiles"][profile.name] = {
                "generated": False,
                "views": list(profile.views),
                "error": str(exc),
            }

            print(
                f"[projection-tool] ERROR {sheet_name}/{profile.name}: {exc}"
            )

    manifest_path = sheet_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"[projection-tool] manifest -> {manifest_path}")


def main() -> None:
    args = parse_args()

    example_dir = args.example_dir.resolve()
    output_dir = args.output_dir.resolve()

    sheets_dir = example_dir / "sheets"

    if not sheets_dir.exists():
        raise FileNotFoundError(
            f"Expected sheets directory: {sheets_dir}"
        )

    sheet_files = sorted(
        sheets_dir.glob("sheet*.png")
    )

    if not sheet_files:
        raise RuntimeError(
            f"No sheet*.png found in {sheets_dir}"
        )

    generated_root = output_dir / "generated"
    generated_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    for sheet_path in sheet_files:
        print("=" * 80)
        print(f"[projection-tool] PROCESS {sheet_path.name}")
        print("=" * 80)

        process_sheet(
            sheet_path,
            generated_root,
            args,
        )


if __name__ == "__main__":
    main()
