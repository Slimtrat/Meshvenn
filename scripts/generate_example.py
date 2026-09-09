from __future__ import annotations

import argparse
import re
import sys
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

ANGLE_PATTERN = re.compile(r"(?<!\d)(\d{1,3})(?:deg|°)?(?!\d)", re.IGNORECASE)
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []

    parser = argparse.ArgumentParser(
        description="Generate a Blender/GLB scan from one example directory."
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
    return parser.parse_args(argv)


def extract_angle(path: Path) -> float | None:
    match = ANGLE_PATTERN.search(path.stem)
    if match:
        return float(int(match.group(1)) % 360)

    lowered = path.stem.lower()
    if "front" in lowered:
        return 0.0
    if "right" in lowered or "side" in lowered:
        return 90.0
    if "back" in lowered:
        return 180.0
    if "left" in lowered:
        return 270.0
    return None


def discover_projection_files(example_dir: Path) -> list[tuple[Path, float]]:
    if not example_dir.exists():
        raise FileNotFoundError(f"Example directory does not exist: {example_dir}")

    candidates = sorted(
        path for path in example_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if len(candidates) < 2:
        raise RuntimeError(
            f"At least two projection images are required in {example_dir}."
        )

    detected = [(path, extract_angle(path)) for path in candidates]

    if any(angle is None for _, angle in detected):
        step = 360.0 / len(detected)
        result = [
            (path, index * step if angle is None else float(angle))
            for index, (path, angle) in enumerate(detected)
        ]
    else:
        result = [(path, float(angle)) for path, angle in detected if angle is not None]

    result.sort(key=lambda item: item[1])
    return result


def blender_image_to_mask(path: Path, alpha_threshold: float):
    image = bpy.data.images.load(str(path.resolve()), check_existing=True)
    image.update()

    width = int(image.size[0])
    height = int(image.size[1])
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid image dimensions for {path}")

    return rgba_to_mask(
        pixels=tuple(image.pixels[:]),
        width=width,
        height=height,
        alpha_threshold=alpha_threshold,
    )


def build_projections(
    projection_files: list[tuple[Path, float]],
    alpha_threshold: float,
) -> list[ProjectionView]:
    projections = []
    for path, angle in projection_files:
        print(f"[projection-tool] load {path.name} @ {angle:.1f}°")
        projections.append(
            ProjectionView(
                mask=blender_image_to_mask(path, alpha_threshold),
                azimuth_degrees=angle,
                elevation_degrees=0.0,
                enabled=True,
            )
        )
    return projections


def clear_scene() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def create_blender_object(vertices, faces) -> bpy.types.Object:
    mesh = bpy.data.meshes.new("ProjectionToolExampleMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    obj = bpy.data.objects.new("ProjectionToolExampleScan", mesh)
    bpy.context.scene.collection.objects.link(obj)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def assert_generated_object(obj: bpy.types.Object) -> None:
    if obj.type != "MESH":
        raise AssertionError("Generated object is not a mesh.")
    if len(obj.data.vertices) <= 0:
        raise AssertionError("Generated mesh has no vertices.")
    if len(obj.data.polygons) <= 0:
        raise AssertionError("Generated mesh has no faces.")

    d = obj.dimensions
    if d.x <= 0 or d.y <= 0 or d.z <= 0:
        raise AssertionError(f"Invalid dimensions: {tuple(d)}")

    print(
        "[projection-tool] validation: "
        f"vertices={len(obj.data.vertices)}, "
        f"faces={len(obj.data.polygons)}, "
        f"dimensions=({d.x:.3f}, {d.y:.3f}, {d.z:.3f})"
    )


def export_outputs(obj: bpy.types.Object, output_dir: Path, name: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    blend_path = output_dir / f"{name}.blend"
    glb_path = output_dir / f"{name}.glb"

    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path.resolve()))

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    # Blender 5.x glTF exporter operator.
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path.resolve()),
        export_format="GLB",
        use_selection=True,
    )

    print(f"[projection-tool] wrote {blend_path}")
    print(f"[projection-tool] wrote {glb_path}")


def generate(args: argparse.Namespace) -> None:
    example_dir = args.example_dir.resolve()
    output_dir = args.output_dir.resolve()

    projection_files = discover_projection_files(example_dir)
    print(
        f"[projection-tool] generating {example_dir} "
        f"from {len(projection_files)} views @ {args.resolution}³"
    )

    clear_scene()

    projections = build_projections(
        projection_files,
        alpha_threshold=args.threshold,
    )

    volume = build_visual_hull(
        projections,
        options=VisualHullOptions(
            resolution=args.resolution,
            symmetry_x=args.symmetry_x,
        ),
    )

    if volume.occupied_count == 0:
        raise RuntimeError(
            "Projection intersection is empty. Check masks, angles and alignment."
        )

    volume = crop_empty_bounds(volume)

    mesh_data = build_surface_mesh(volume, voxel_size=1.0, center=True)
    mesh_data = scale_mesh_to_height(mesh_data, args.target_height)

    obj = create_blender_object(mesh_data.vertices, mesh_data.faces)

    cleanup_generated_object(
        obj,
        auto_remesh=not args.no_remesh,
        voxel_size=args.voxel_size,
        smooth_iterations=args.smooth,
    )

    obj["bpt_projection_count"] = len(projections)
    obj["bpt_resolution"] = args.resolution
    obj["bpt_occupied_voxels"] = volume.occupied_count

    assert_generated_object(obj)
    export_outputs(obj, output_dir, example_dir.name)


def main() -> None:
    generate(parse_args())


if __name__ == "__main__":
    main()
