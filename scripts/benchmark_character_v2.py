"""Run the complete GLB -> views -> geometry -> rig -> posed GLB benchmark.

RiggedFigure's source armature is used only to record scoring landmarks. The
rendered input is a newly exported, unrigged rest mesh, and the generated rig
receives only the native reconstruction produced from those pixels.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy

from scripts.benchmark_glb_v2 import create_blank_template, reconstruct, render_projection
from scripts.benchmark_rig_v2 import (
    EXPECTED_BONES,
    _package_modules,
    _pose_response,
    _skin_rows,
    _unrigged_world_mesh,
)
from scripts.glb_v2_animation_fixture import (
    animated_glb_roundtrip,
    inspect_isolated_reference,
)
from scripts.generate_example_native_support.extraction import extract_sheet
from scripts.glb_v2_character_support import assert_unrigged_mesh, normalized_landmarks
from scripts.glb_v2_metrics import score_silhouettes
from scripts.glb_v2_rig_metrics import landmark_summary, skin_weight_summary
from scripts.glb_v2_surface_metrics import compare_glb_surfaces
from scripts.render_turntable import clear_scene
from scripts.run_logger import RunLogger


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resolution", type=int, default=48)
    parser.add_argument(
        "--rig-implementation",
        choices=("canonical-biped-v1", "canonical-biped-v2"),
        default="canonical-biped-v1",
    )
    parser.add_argument("--min-iou", type=float, default=0.65)
    parser.add_argument("--min-surface-fscore", type=float, default=0.85)
    parser.add_argument("--max-extent-error", type=float, default=0.25)
    parser.add_argument("--max-mean-joint-error", type=float, default=0.10)
    parser.add_argument("--max-joint-error", type=float, default=0.16)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def _world_vertices(mesh: bpy.types.Object) -> list[tuple[float, float, float]]:
    return [tuple(mesh.matrix_world @ vertex.co) for vertex in mesh.data.vertices]


def _export_unrigged_reference(source_path: Path, output_path: Path) -> tuple[dict, list, dict]:
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(source_path.resolve()))
    armature = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    source_mesh = max(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH" and any(
            modifier.type == "ARMATURE" for modifier in obj.modifiers
        )),
        key=lambda obj: len(obj.data.vertices),
    )
    reference_heads = {
        bone.name: tuple(armature.matrix_world @ bone.head_local)
        for bone in armature.data.bones
    }
    reference_vertices = _world_vertices(source_mesh)
    unrigged = _unrigged_world_mesh(source_mesh)
    assert_unrigged_mesh(unrigged)
    for selected in tuple(bpy.context.selected_objects):
        selected.select_set(False)
    unrigged.select_set(True)
    bpy.context.view_layer.objects.active = unrigged
    result = bpy.ops.export_scene.gltf(
        filepath=str(output_path.resolve()), export_format="GLB", use_selection=True
    )
    if "FINISHED" not in result or not output_path.is_file():
        raise AssertionError("Could not create isolated unrigged reference GLB")
    isolation = inspect_isolated_reference(output_path)
    return reference_heads, reference_vertices, isolation


def _rig_reconstruction(
    generated_glb: Path, output: Path, resolution: int, implementation_id: str
) -> dict:
    geometry_contracts, pipeline, rig_module = _package_modules(implementation_id)
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(generated_glb.resolve()))
    mesh = max(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
        key=lambda obj: len(obj.data.vertices),
    )
    assert_unrigged_mesh(mesh)
    context = pipeline.PipelineContext(scene=bpy.context.scene)
    geometry = geometry_contracts.GeometrySurfaceOutput(
        blender_object=mesh,
        source=object(),
        projection_space=geometry_contracts.GeometryProjectionSpace(
            resolution, resolution, resolution
        ),
        implementation_id="native-visual-hull",
    )
    context.set_output(pipeline.PipelineStage.GEOMETRY, geometry)
    implementation_class = getattr(
        rig_module, "CanonicalRigV2Implementation", None
    ) or rig_module.CanonicalRigImplementation
    implementation = implementation_class()
    availability = implementation.availability(context)
    if not availability.ready:
        raise AssertionError(f"Reconstructed biped rejected by rig: {availability.reason}")
    result = implementation.execute(context)
    if not result.success:
        raise AssertionError(f"Reconstructed biped rig failed: {result.message}")
    rig = result.payload
    if set(rig.armature_object.data.bones.keys()) != EXPECTED_BONES:
        raise AssertionError("Reconstructed biped produced the wrong canonical bone set")
    candidate_heads = {
        bone.name: tuple(rig.armature_object.matrix_world @ bone.head_local)
        for bone in rig.armature_object.data.bones
    }
    candidate_vertices = _world_vertices(mesh)
    weights = skin_weight_summary(_skin_rows(mesh, rig.armature_object))
    pose = _pose_response(mesh, rig.armature_object)
    roundtrip = animated_glb_roundtrip(mesh, rig.armature_object, output / "character_animated.glb")
    return {
        "rig_implementation": rig.implementation_id,
        "binding_method": rig.binding_method,
        "quality": result.metadata["rig_quality"],
        "candidate_heads": candidate_heads,
        "candidate_vertices": candidate_vertices,
        "skin_weights": weights,
        "pose_response": pose,
        "glb_roundtrip": roundtrip,
    }


def main() -> None:
    args = arguments()
    thresholds = (
        args.min_iou, args.min_surface_fscore, args.max_extent_error,
        args.max_mean_joint_error, args.max_joint_error,
    )
    if args.resolution < 16 or any(not 0.0 <= value <= 1.0 for value in thresholds):
        raise ValueError("resolution must be >= 16 and thresholds must be between 0 and 1")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((REPO_ROOT / "example" / "v2" / "manifest.json").read_text("utf-8"))
    asset = next(item for item in manifest["assets"] if item["id"] == "rigged_figure")
    source_path = REPO_ROOT / "example" / "v2" / asset["file"]
    isolated_path = output / "reference_unrigged.glb"
    reference_heads, reference_vertices, isolation = _export_unrigged_reference(
        source_path, isolated_path
    )

    template = output / "blank_template.png"
    source_sheet = output / "source_sheet.png"
    reconstruction_sheet = output / "reconstruction_sheet.png"
    create_blank_template(template)
    render_projection(isolated_path, template, source_sheet)
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
    silhouette = score_silhouettes(reference_views, candidate_views)
    surface = compare_glb_surfaces(isolated_path, generated_glb)
    rig = _rig_reconstruction(
        generated_glb, output, args.resolution, args.rig_implementation
    )
    reference_normalized = normalized_landmarks(reference_heads, reference_vertices)
    candidate_normalized = normalized_landmarks(
        rig.pop("candidate_heads"), rig.pop("candidate_vertices")
    )
    landmarks = landmark_summary(reference_normalized, candidate_normalized, 1.0)
    acceptance = {
        "minimum_silhouette_iou": args.min_iou,
        "minimum_surface_fscore": args.min_surface_fscore,
        "maximum_extent_error": args.max_extent_error,
        "maximum_mean_joint_error_in_heights": args.max_mean_joint_error,
        "maximum_joint_error_in_heights": args.max_joint_error,
        "minimum_skin_coverage": 1.0,
        "maximum_influences_per_vertex": 4,
        "maximum_weight_sum_error": 0.02,
        "minimum_left_pose_peak_displacement": 0.02,
        "maximum_right_pose_peak_displacement": 0.001,
    }
    report = {
        "schema_version": 1,
        "pipeline": "source GLB -> isolated rest mesh -> ten views -> native geometry -> canonical rig -> posed GLB",
        "source_asset": asset["id"],
        "source_sha256": asset["sha256"],
        "source_rig_isolation": {
            **isolation,
            "armature_passed_to_reconstruction": False,
            "skin_weights_passed_to_reconstruction": False,
            "reference_armature_used_for": "normalized landmark scoring only",
        },
        "resolution": args.resolution,
        "acceptance": acceptance,
        "silhouette": silhouette,
        "surface_3d": surface,
        "landmarks": landmarks,
        **rig,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    print(
        f"Character E2E: IoU={silhouette['mean_iou']:.4f}; "
        f"surface F-score={surface['surface_fscore']:.4f}; "
        f"joint mean={landmarks['mean_error_in_heights']:.4f}; "
        f"skin={rig['skin_weights']['weighted_fraction']:.3f}"
    )
    if silhouette["valid_input_views"] != silhouette["total_views"]:
        raise AssertionError("Character source rendering contains invalid views")
    if (
        silhouette["mean_iou"] < args.min_iou
        or surface["surface_fscore"] < args.min_surface_fscore
        or surface["max_extent_error"] > args.max_extent_error
    ):
        raise AssertionError("Character reconstruction fell below its geometry contract")
    if landmarks["mean_error_in_heights"] > args.max_mean_joint_error:
        raise AssertionError("Character mean joint placement fell below its rig contract")
    if landmarks["max_error_in_heights"] > args.max_joint_error:
        raise AssertionError("Character worst joint placement fell below its rig contract")
    weights = rig["skin_weights"]
    roundtrip = rig["glb_roundtrip"]
    if weights["weighted_fraction"] < 1.0 or weights["max_influences_per_vertex"] > 4:
        raise AssertionError("Character skinning coverage or influence count regressed")
    if weights["max_weight_sum_error"] > 0.02:
        raise AssertionError("Character skin weights are not normalized")
    pose = rig["pose_response"]
    if pose["left_max_displacement"] <= acceptance["minimum_left_pose_peak_displacement"]:
        raise AssertionError("Character pose did not deform the requested arm")
    if pose["right_max_displacement"] > acceptance["maximum_right_pose_peak_displacement"]:
        raise AssertionError("Character pose leaked into the opposite arm")
    if roundtrip["weighted_fraction"] < 1.0 or roundtrip["max_influences_per_vertex"] > 4:
        raise AssertionError("Character GLB roundtrip lost usable skinning")
    if roundtrip["max_weight_sum_error"] > acceptance["maximum_weight_sum_error"]:
        raise AssertionError("Character GLB roundtrip lost normalized skin weights")
    if roundtrip["animation_count"] < 1:
        raise AssertionError("Character GLB roundtrip lost its animation")
    if roundtrip["left_max_displacement"] <= acceptance["minimum_left_pose_peak_displacement"]:
        raise AssertionError("Imported character animation did not deform the requested arm")
    if roundtrip["right_max_displacement"] > acceptance["maximum_right_pose_peak_displacement"]:
        raise AssertionError("Imported character animation leaked into the opposite arm")


if __name__ == "__main__":
    main()
