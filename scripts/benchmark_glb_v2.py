"""Import the V2 GLB corpus and benchmark GLB -> views -> native GLB.

Run inside Blender, with a built native library in native/bin. Only the
rendered sheet is passed into reconstruction; the reference mesh stays hidden.
"""

from __future__ import annotations

import argparse
import json
import sys
from array import array
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy

from scripts.generate_example_native_support.extraction import extract_sheet
from scripts.generate_example_native_support.pipeline import process_sheet
from scripts.glb_v2_metrics import score_silhouettes
from scripts.render_projection_sheet_support.pipeline import main as render_sheet
from scripts.render_turntable import clear_scene
from scripts.run_logger import RunLogger


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", default="avocado")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=48)
    parser.add_argument("--min-iou", type=float, default=0.10)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def verify_blender_imports(assets: list[dict], root: Path) -> list[dict]:
    results = []
    for asset in assets:
        clear_scene()
        before_actions = set(bpy.data.actions)
        path = root / asset["file"]
        bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
        new_actions = set(bpy.data.actions) - before_actions
        if not meshes or not all(len(obj.data.polygons) for obj in meshes):
            raise AssertionError(f"{asset['id']}: Blender did not import mesh faces")
        if asset["skins"] and not armatures:
            raise AssertionError(f"{asset['id']}: Blender did not import an armature")
        if asset["animations"] and not new_actions:
            raise AssertionError(f"{asset['id']}: Blender did not import animations")
        results.append({
            "asset": asset["id"],
            "blender_mesh_objects": len(meshes),
            "blender_armatures": len(armatures),
            "blender_actions": len(new_actions),
        })
        print(f"V2 import OK: {asset['id']} ({len(meshes)} mesh objects, {len(armatures)} armatures)")
    clear_scene()
    return results


def create_blank_template(path: Path, *, width: int = 1000, height: int = 600) -> None:
    image = bpy.data.images.new("V2_BlankProjectionSheet", width=width, height=height, alpha=True)
    try:
        image.pixels.foreach_set(array("f", (1.0,)) * (width * height * 4))
        image.filepath_raw = str(path.resolve())
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def render_projection(input_glb: Path, template: Path, output: Path) -> None:
    previous_argv = sys.argv
    sys.argv = ["blender", "--", "--input", str(input_glb), "--template", str(template),
                "--output", str(output), "--samples", "1", "--material-mode", "neutral"]
    try:
        render_sheet()
    finally:
        sys.argv = previous_argv


def reconstruct(source_sheet: Path, output: Path, resolution: int) -> Path:
    options = argparse.Namespace(
        resolution=resolution, threshold=0.1, sheet_white_threshold=0.94,
        profiles=["L10"], thread_count=0, symmetry_x=False, voxel_size=1.0,
        target_height=2.0, mesh_mode="surface_nets", skip_blend=True,
    )
    generated_root = output / "generated"
    process_sheet(source_sheet, generated_root, options, logger=RunLogger())
    result = generated_root / source_sheet.stem / "scans" / "L10" / f"{source_sheet.stem}_L10.glb"
    if not result.is_file():
        raise AssertionError(f"Native reconstruction produced no GLB: {result}")
    return result


def main() -> None:
    args = arguments()
    if args.resolution < 16 or not 0.0 <= args.min_iou <= 1.0:
        raise ValueError("resolution must be >= 16 and min-iou must be between 0 and 1")
    root = REPO_ROOT / "example" / "v2"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assets = manifest["assets"]
    selected = next((asset for asset in assets if asset["id"] == args.asset), None)
    if selected is None or selected["skins"]:
        raise ValueError("Choose one static geometry asset from the V2 manifest")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    imports = verify_blender_imports(assets, root)
    template = output / "blank_template.png"
    source_sheet = output / "source_sheet.png"
    reconstruction_sheet = output / "reconstruction_sheet.png"
    create_blank_template(template)
    render_projection(root / selected["file"], template, source_sheet)
    generated_glb = reconstruct(source_sheet, output, args.resolution)
    render_projection(generated_glb, template, reconstruction_sheet)
    reference_views, _ = extract_sheet(
        source_sheet, output / "reference_views", white_threshold=0.94,
        alpha_threshold=0.1, logger=RunLogger(),
    )
    candidate_views, _ = extract_sheet(
        reconstruction_sheet, output / "candidate_views", white_threshold=0.94,
        alpha_threshold=0.1, logger=RunLogger(),
    )
    score = score_silhouettes(reference_views, candidate_views)
    report = {
        "schema_version": 1,
        "source_asset": selected["id"],
        "source_sha256": selected["sha256"],
        "resolution": args.resolution,
        "profile": "L10",
        "metric": "mean ten-view silhouette IoU",
        "minimum_smoke_iou": args.min_iou,
        "imports": imports,
        **score,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"V2 benchmark score: {score['mean_iou']:.4f} ({score['valid_input_views']}/{score['total_views']} valid source views)")
    if score["valid_input_views"] != score["total_views"] or score["mean_iou"] < args.min_iou:
        raise AssertionError("V2 source rendering or reconstruction fell below the smoke contract")


if __name__ == "__main__":
    main()
