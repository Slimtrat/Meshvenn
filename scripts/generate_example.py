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

from core.cleanup import cleanup_generated_object
from core.masks import rgba_to_mask
from core.mesh_builder import build_surface_mesh, scale_mesh_to_height
from core.visual_hull import (
    ProjectionView,
    VisualHullOptions,
    VisualHullSession,
    crop_empty_bounds,
)
from scripts.run_logger import RunLogger
from scripts.scan_profiles import PROFILES


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

# Order chosen so snapshots can reuse all work:
# L2 -> L4 -> L8 -> L10.
INCREMENTAL_VIEW_ORDER = (
    "000",
    "090",
    "180",
    "270",
    "045",
    "135",
    "225",
    "315",
    "TOP",
    "BOT",
)

PROFILE_AFTER_VIEW = {
    "090": "L2",
    "270": "L4",
    "315": "L8",
    "BOT": "L10",
}


@dataclass(frozen=True)
class ExtractedView:
    name: str
    path: Path
    azimuth_degrees: float
    elevation_degrees: float
    bbox: tuple[int, int, int, int]
    sha256: str
    valid: bool


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
    y0 = round((1.0 - bottomn) * image_height)
    y1 = round((1.0 - topn) * image_height)

    return x0, y0, x1, y1


def _largest_component(
    foreground: bytearray,
    width: int,
    height: int,
) -> set[int]:
    visited = bytearray(width * height)
    largest: set[int] = set()

    for start, is_foreground in enumerate(foreground):
        if visited[start] or not is_foreground:
            continue

        visited[start] = 1
        stack = [start]
        component: set[int] = set()

        while stack:
            index = stack.pop()
            component.add(index)

            x = index % width
            y = index // width

            if x > 0:
                neighbor = index - 1
                if foreground[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    stack.append(neighbor)

            if x + 1 < width:
                neighbor = index + 1
                if foreground[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    stack.append(neighbor)

            if y > 0:
                neighbor = index - width
                if foreground[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    stack.append(neighbor)

            if y + 1 < height:
                neighbor = index + width
                if foreground[neighbor] and not visited[neighbor]:
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
    sheet_width = int(sheet.size[0])
    source = sheet.pixels

    rgba = [0.0] * (width * height * 4)
    foreground = bytearray(width * height)

    for local_y in range(height):
        source_y = y0 + local_y
        source_row = source_y * sheet_width

        for local_x in range(width):
            source_x = x0 + local_x
            source_index = (source_row + source_x) * 4
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

            foreground[pixel_index] = 1 if (
                alpha > 0.01
                and not (
                    red >= white_threshold
                    and green >= white_threshold
                    and blue >= white_threshold
                )
            ) else 0

    component = _largest_component(foreground, width, height)
    minimum_component = max(64, int(width * height * 0.005))
    valid = len(component) >= minimum_component

    if valid:
        keep = component
        for pixel_index in range(width * height):
            if pixel_index not in keep:
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
    logger: RunLogger,
) -> tuple[list[ExtractedView], dict]:
    output_dir.mkdir(parents=True, exist_ok=True)

    sheet = bpy.data.images.load(str(sheet_path.resolve()), check_existing=False)
    sheet.update()

    image_width = int(sheet.size[0])
    image_height = int(sheet.size[1])
    extracted_views: list[ExtractedView] = []

    logger.info("Sheet loaded", width=image_width, height=image_height)

    try:
        for index, (name, column, row, azimuth, elevation) in enumerate(
            CELL_SPECS,
            start=1,
        ):
            logger.progress(index, len(CELL_SPECS), f"extract {name}")

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
                "output": view.path.name,
                "sha256": view.sha256,
                "valid": view.valid,
            }
            for view in extracted_views
        ],
        "available_views": [view.name for view in extracted_views if view.valid],
    }

    return extracted_views, manifest


def image_to_mask(path: Path, alpha_threshold: float):
    image = bpy.data.images.load(str(path.resolve()), check_existing=False)
    image.update()

    try:
        return rgba_to_mask(
            pixels=tuple(image.pixels[:]),
            width=int(image.size[0]),
            height=int(image.size[1]),
            alpha_threshold=alpha_threshold,
        )
    finally:
        bpy.data.images.remove(image)


def prepare_projections(
    views: list[ExtractedView],
    threshold: float,
    logger: RunLogger,
) -> dict[str, ProjectionView]:
    projections: dict[str, ProjectionView] = {}

    valid = [view for view in views if view.valid]
    for index, view in enumerate(valid, start=1):
        logger.progress(index, len(valid), f"mask {view.name}")
        mask = image_to_mask(view.path, threshold)

        projections[view.name] = ProjectionView(
            mask=mask,
            azimuth_degrees=view.azimuth_degrees,
            elevation_degrees=view.elevation_degrees,
            enabled=True,
        )

    return projections


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

    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path.resolve()))

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    bpy.ops.export_scene.gltf(
        filepath=str(glb_path.resolve()),
        export_format="GLB",
        use_selection=True,
    )

    return {
        "blend": str(blend_path),
        "glb": str(glb_path),
        "vertices": len(obj.data.vertices),
        "faces": len(obj.data.polygons),
        "dimensions": [float(value) for value in obj.dimensions],
    }


def build_export_from_volume(
    volume,
    *,
    profile_name: str,
    scan_dir: Path,
    file_stem: str,
    args: argparse.Namespace,
    logger: RunLogger,
) -> dict:
    with logger.timed("crop bounds"):
        cropped = crop_empty_bounds(volume)

    with logger.timed("build surface mesh"):
        mesh_data = build_surface_mesh(
            cropped,
            voxel_size=1.0,
            center=True,
        )

    with logger.timed("scale mesh"):
        mesh_data = scale_mesh_to_height(
            mesh_data,
            args.target_height,
        )

    clear_scene()

    with logger.timed("create Blender object"):
        obj = create_object(mesh_data.vertices, mesh_data.faces)

    with logger.timed("cleanup mesh"):
        cleanup_generated_object(
            obj,
            auto_remesh=not args.no_remesh,
            voxel_size=args.voxel_size,
            smooth_iterations=args.smooth,
        )

    with logger.timed("export"):
        result = export_scan(obj, scan_dir, file_stem)

    result.update(
        {
            "profile": profile_name,
            "resolution": args.resolution,
            "occupied_voxels": volume.occupied_count,
            "occupancy_ratio": volume.occupancy_ratio,
        }
    )

    return result


def generate_profiles_incrementally(
    projections: dict[str, ProjectionView],
    *,
    scans_root: Path,
    sheet_name: str,
    args: argparse.Namespace,
    logger: RunLogger,
) -> dict[str, dict]:
    profiles_by_name = {profile.name: profile for profile in PROFILES}
    requested = (
        {name.upper() for name in args.profiles}
        if args.profiles
        else set(profiles_by_name)
    )

    runnable = {
        name
        for name in requested
        if name in profiles_by_name
        and set(profiles_by_name[name].views).issubset(projections)
    }

    if not runnable:
        return {}

    max_level = max(
        ("L2", "L4", "L8", "L10").index(name)
        for name in runnable
    )
    max_profile = ("L2", "L4", "L8", "L10")[max_level]
    required_views = set(profiles_by_name[max_profile].views)

    session = VisualHullSession(
        options=VisualHullOptions(
            resolution=args.resolution,
            symmetry_x=args.symmetry_x,
        )
    )

    results: dict[str, dict] = {}
    applied = 0

    with logger.section(
        "incremental visual hull",
        target=max_profile,
        initial_voxels=args.resolution ** 3,
    ):
        for view_name in INCREMENTAL_VIEW_ORDER:
            if view_name not in required_views:
                continue
            if view_name not in projections:
                continue

            before = session.alive_count
            with logger.timed(
                f"apply view {view_name}",
                surviving_before=before,
            ):
                after = session.apply_view(
                    projections[view_name],
                    name=view_name,
                )

            applied += 1
            removed = before - after
            logger.info(
                "view result",
                view=view_name,
                surviving=after,
                removed=removed,
                removed_pct=f"{(removed / before * 100.0) if before else 0.0:.1f}%",
            )

            profile_name = PROFILE_AFTER_VIEW.get(view_name)
            if profile_name is None or profile_name not in runnable:
                continue

            profile = profiles_by_name[profile_name]

            # Snapshot is cheap compared with rebuilding the hull and makes
            # each generated level independent from later views.
            volume = session.snapshot()

            profile_logger = logger.child(indent_offset=1)
            with profile_logger.section(
                f"snapshot {profile_name}",
                views=", ".join(profile.views),
                occupied_voxels=volume.occupied_count,
            ):
                try:
                    result = build_export_from_volume(
                        volume,
                        profile_name=profile_name,
                        scan_dir=scans_root / profile_name,
                        file_stem=f"{sheet_name}_{profile_name}",
                        args=args,
                        logger=profile_logger,
                    )
                    result["generated"] = True
                    result["views"] = list(profile.views)
                    result["applied_projection_count"] = applied
                    results[profile_name] = result
                except Exception as exc:
                    results[profile_name] = {
                        "generated": False,
                        "views": list(profile.views),
                        "error": str(exc),
                    }
                    profile_logger.error(
                        f"{profile_name} export failed",
                        error=str(exc),
                    )

    return results


def process_sheet(
    sheet_path: Path,
    generated_root: Path,
    args: argparse.Namespace,
    logger: RunLogger | None = None,
) -> None:
    sheet_name = sheet_path.stem
    sheet_root = generated_root / sheet_name
    extracted_dir = sheet_root / "extracted"
    scans_root = sheet_root / "scans"

    sheet_root.mkdir(parents=True, exist_ok=True)
    jsonl_path = sheet_root / "run_log.jsonl" if getattr(args, "json_log", False) else None
    logger = logger or RunLogger(jsonl_path=jsonl_path)

    with logger.section(
        f"sheet {sheet_name}",
        source=str(sheet_path),
    ):
        with logger.timed("extract sheet"):
            views, manifest = extract_presheet(
                sheet_path,
                extracted_dir,
                white_threshold=args.sheet_white_threshold,
                logger=logger.child(indent_offset=1),
            )

        with logger.timed("prepare masks once"):
            projections = prepare_projections(
                views,
                args.threshold,
                logger.child(indent_offset=1),
            )

        logger.info(
            "prepared views",
            count=len(projections),
            views=", ".join(projections),
        )

        with logger.timed("generate all requested profiles incrementally"):
            manifest["profiles"] = generate_profiles_incrementally(
                projections,
                scans_root=scans_root,
                sheet_name=sheet_name,
                args=args,
                logger=logger.child(indent_offset=1),
            )

        manifest_path = sheet_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.success("manifest written", path=str(manifest_path))


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
    parser.add_argument("--sheet-white-threshold", type=float, default=0.94)
    parser.add_argument("--profiles", nargs="*", default=None)
    parser.add_argument("--json-log", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    example_dir = args.example_dir.resolve()
    output_dir = args.output_dir.resolve()
    sheets_dir = example_dir / "sheets"

    if not sheets_dir.exists():
        raise FileNotFoundError(f"Expected sheets directory: {sheets_dir}")

    sheet_files = sorted(sheets_dir.glob("sheet*.png"))
    if not sheet_files:
        raise RuntimeError(f"No sheet*.png found in {sheets_dir}")

    generated_root = output_dir / "generated"
    generated_root.mkdir(parents=True, exist_ok=True)

    logger = RunLogger()
    for index, sheet_path in enumerate(sheet_files, start=1):
        logger.progress(index, len(sheet_files), sheet_path.name)
        process_sheet(
            sheet_path,
            generated_root,
            args,
            logger=logger.child(indent_offset=1),
        )


if __name__ == "__main__":
    main()
