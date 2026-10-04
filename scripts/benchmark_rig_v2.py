"""Benchmark canonical fitting from real, verified unrigged GLB inputs.

The source armature is used only for scoring, then removed. Meshvenn receives
a GLB with no skin, animation or groups through its normal INPUT/GEOMETRY path.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bpy
from mathutils.kdtree import KDTree

from scripts.glb_v2_rig_metrics import landmark_summary, landmark_group_summary, skin_weight_summary
from scripts.glb_v2_character_support import assert_unrigged_mesh
from scripts.glb_v2_pose_support import evaluated_positions as _evaluated_positions, rotated_bone, pose_quality
from scripts.glb_v2_pose_metrics import pose_acceptance, check_pose_quality, check_pose_roundtrip


EXPECTED_BONES = {
    "root", "pelvis", "spine", "chest", "neck", "head",
    *(f"{part}.{side}" for side in ("L", "R") for part in (
        "upper_arm", "forearm", "hand", "thigh", "shin", "foot"
    )),
}
LEG_JOINTS = tuple(f"{part}.{side}" for side in ("L", "R") for part in ("thigh", "shin", "foot"))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset", choices=("rigged_figure", "quaternius_human", "quaternius_ual1"),
                        default="rigged_figure")
    parser.add_argument(
        "--implementation",
        choices=("canonical-biped-v1", "canonical-biped-v2"),
        default="canonical-biped-v1",
    )
    parser.add_argument("--max-mean-joint-error", type=float, default=0.15)
    parser.add_argument("--max-joint-error", type=float, default=0.20)
    parser.add_argument("--max-arm-unrelated-weight", type=float, default=1.0)
    parser.add_argument("--max-mean-leg-joint-error", type=float, default=1.0)
    parser.add_argument("--max-leg-joint-error", type=float, default=1.0)
    parser.add_argument("--max-leg-unrelated-weight", type=float, default=1.0)
    parser.add_argument("--require-observed-leg-cues", action="store_true")
    parser.add_argument("--check-leg-deformation", action="store_true")
    parser.add_argument("--check-pose-quality", action="store_true",
                        help="Enforce the fixture's 16-pose local edge-distortion budgets")
    parser.add_argument("--check-hinge-quality", action="store_true",
                        help="Enforce the fixture's 24-pose elbow/knee distortion budgets")
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(argv)
    for name in ("max_mean_joint_error", "max_joint_error", "max_arm_unrelated_weight",
                 "max_mean_leg_joint_error", "max_leg_joint_error", "max_leg_unrelated_weight"):
        if not math.isfinite(getattr(args,name)) or getattr(args,name) < 0:
            parser.error(f"{name.replace('_','-')} must be finite and nonnegative")
    return args


def _package_modules(implementation_id: str = "canonical-biped-v1"):
    module_name = (
        "canonical_rig_v2" if implementation_id == "canonical-biped-v2"
        else "canonical_rig"
    )
    package_name = REPO_ROOT.name
    importlib.import_module(package_name)
    return (
        importlib.import_module(f"{package_name}.core.geometry_contracts"),
        importlib.import_module(f"{package_name}.core.pipeline_contracts"),
        importlib.import_module(f"{package_name}.implementations.{module_name}"),
    )


def _unrigged_world_mesh(source: bpy.types.Object) -> bpy.types.Object:
    vertices = [tuple(source.matrix_world @ vertex.co) for vertex in source.data.vertices]
    faces = [tuple(polygon.vertices) for polygon in source.data.polygons]
    mesh = bpy.data.meshes.new("V2_Reference_UnriggedMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for material in source.data.materials:
        mesh.materials.append(material)
    for original, copy in zip(source.data.polygons, mesh.polygons):
        copy.material_index = original.material_index
        copy.use_smooth = original.use_smooth
    for source_layer in source.data.uv_layers:
        layer = mesh.uv_layers.new(name=source_layer.name)
        for original, copy in zip(source_layer.data, layer.data):
            copy.uv = original.uv
    obj = bpy.data.objects.new("V2_Reference_Unrigged", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _skin_rows(mesh: bpy.types.Object, armature: bpy.types.Object) -> list[list[float]]:
    deform = {bone.name for bone in armature.data.bones if bone.use_deform}
    indices = {group.index for group in mesh.vertex_groups if group.name in deform}
    return [
        [member.weight for member in vertex.groups if member.group in indices]
        for vertex in mesh.data.vertices
    ]


def _pose_response(mesh: bpy.types.Object, armature: bpy.types.Object, region_indices=None,
                   *, posed_bone="upper_arm.L", rotation_axis=1) -> dict:
    rest = _evaluated_positions(mesh)
    direction = tuple(1 if index == rotation_axis else 0 for index in range(3))
    with rotated_bone(armature, posed_bone, 35, direction):
        posed = _evaluated_positions(mesh)
    if len(rest) != len(posed):
        raise AssertionError("Pose changed mesh topology")
    if region_indices:
        family = "arm" if posed_bone.startswith("upper_arm") else "leg"
        left = [math.dist(rest[index], posed[index]) for index in region_indices[f"{family}.L"]]
        right = [math.dist(rest[index], posed[index]) for index in region_indices[f"{family}.R"]]
    else:
        left = [math.dist(before, after) for before, after in zip(rest, posed) if before[0] > 0.10]
        right = [math.dist(before, after) for before, after in zip(rest, posed) if before[0] < -0.10]
    if not left or not right:
        raise AssertionError("Reference figure lacks bilateral pose samples")
    return {
        "posed_bone": posed_bone,
        "angle_degrees": 35,
        "left_mean_displacement": sum(left) / len(left),
        "right_mean_displacement": sum(right) / len(right),
        "left_max_displacement": max(left),
        "right_max_displacement": max(right),
    }


def _roundtrip(mesh: bpy.types.Object, armature: bpy.types.Object, path: Path, context, reference_regions) -> dict:
    for selected in tuple(bpy.context.selected_objects):
        selected.select_set(False)
    mesh.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    package = REPO_ROOT.name
    context.metadata.update(export_output_path=str(path), export_overwrite_existing=True,
                            export_validate_roundtrip=True)
    exporter = importlib.import_module(f"{package}.implementations.glb_export").GLBExportImplementation()
    result = exporter.execute(context)
    if not result.success:
        raise AssertionError(f"Canonical rig GLB export failed: {result.message}")
    before = {obj.as_pointer() for obj in bpy.data.objects}
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()), bone_heuristic="TEMPERANCE")
    imported = [obj for obj in bpy.data.objects if obj.as_pointer() not in before]
    arms = [obj for obj in imported if obj.type == "ARMATURE"]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if len(arms) != 1 or not meshes or set(arms[0].data.bones.keys()) != EXPECTED_BONES:
        raise AssertionError("GLB roundtrip lost canonical bones or mesh")
    bound = [obj for obj in meshes if any(
        modifier.type == "ARMATURE" and modifier.object is arms[0] for modifier in obj.modifiers
    )]
    if len(bound) != 1:
        raise AssertionError("GLB roundtrip lost skin binding")
    weights = skin_weight_summary(_skin_rows(bound[0], arms[0]))
    regions, leakage = _limb_region_quality(bound[0], reference_regions)
    return {"glb_bytes": path.stat().st_size, "bone_count": len(arms[0].data.bones),
            "fidelity": context.metadata["glb_export_roundtrip"],
            "pose_response": _pose_response(bound[0], arms[0], regions),
            "leg_pose_response": _pose_response(bound[0], arms[0], regions, posed_bone="thigh.L", rotation_axis=0),
            "pose_quality": pose_quality(bound[0], arms[0], regions),
            "hinge_pose_quality": pose_quality(bound[0], arms[0], regions, hinges=True),
            "arm_region_leakage": {label: value for label,value in leakage.items() if label.startswith("arm")},
            "leg_region_leakage": {label: value for label,value in leakage.items() if label.startswith("leg")}, **weights}


def _source_limb_regions(mesh, armature, correspondence):
    ancestors = {correspondence[f"{root}.{side}"]: f"{label}.{side}"
                 for root,label in (("upper_arm","arm"),("thigh","leg")) for side in ("L","R")}
    labels = {}
    for bone in armature.data.bones:
        ancestor = bone
        while ancestor is not None and ancestor.name not in ancestors:
            ancestor = ancestor.parent
        if ancestor is not None:
            labels[bone.name] = ancestors[ancestor.name]
    groups = {group.index: labels.get(group.name) for group in mesh.vertex_groups}
    result = []
    for vertex in mesh.data.vertices:
        mass = {label: sum(item.weight for item in vertex.groups if groups.get(item.group) == label)
                for label in ("arm.L", "arm.R", "leg.L", "leg.R")}
        label = max(mass, key=mass.get)
        result.append((tuple(mesh.matrix_world @ vertex.co), label if mass[label] >= .7 else None))
    return result


def _limb_region_quality(mesh, reference_regions):
    tree = KDTree(len(reference_regions))
    for index, (point, _) in enumerate(reference_regions):
        tree.insert(point, index)
    tree.balance()
    regions = {"arm.L": [], "arm.R": [], "leg.L": [], "leg.R": []}
    leakage = {label: [] for label in regions}
    for vertex in mesh.data.vertices:
        _, index, distance = tree.find(mesh.matrix_world @ vertex.co)
        if distance > 1.0e-5:
            raise AssertionError("Cannot locate the source-skin scoring region after GLB import")
        label = reference_regions[index][1]
        if label is None:
            continue
        regions[label].append(vertex.index)
        parts = ("upper_arm", "forearm", "hand") if label.startswith("arm") else ("thigh", "shin", "foot")
        allowed = {f"{part}.{label[-1]}" for part in parts}
        leakage[label].append(sum(item.weight for item in vertex.groups
                                  if mesh.vertex_groups[item.group].name not in allowed))
    if not all(regions.values()):
        raise AssertionError("Source fixture has no confidently weighted limb vertices")
    return regions, {label: {"vertex_count": len(values), "mean_unrelated_weight": sum(values) / len(values),
                            "max_unrelated_weight": max(values)} for label, values in leakage.items()}


def _prepare_unrigged_input(source_mesh, reference_heads, reference_regions, output, pipeline):
    """Delete source rig data before the product ever opens its GLB input."""
    neutral = _unrigged_world_mesh(source_mesh)
    assert_unrigged_mesh(neutral)
    points = [tuple(vertex.co) for vertex in neutral.data.vertices]
    minimum = tuple(min(p[i] for p in points) for i in range(3))
    maximum = tuple(max(p[i] for p in points) for i in range(3))
    scale = 2.0 / max(high - low for low, high in zip(minimum, maximum))
    origin = ((minimum[0] + maximum[0]) / 2, (minimum[1] + maximum[1]) / 2, minimum[2])
    normalized_heads = {name: tuple((v - o) * scale for v, o in zip(point, origin))
                        for name, point in reference_heads.items()}
    normalized_regions = [(tuple((v - o) * scale for v, o in zip(point, origin)), label)
                          for point, label in reference_regions]
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    neutral.select_set(True)
    bpy.context.view_layer.objects.active = neutral
    path = output / "unrigged-input.glb"
    result = bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                                     export_animations=False, export_skins=False)
    if "FINISHED" not in result:
        raise AssertionError("Cannot export neutral reference geometry")
    manifest = importlib.import_module(f"{REPO_ROOT.name}.implementations.glb_export.manifest")
    source = manifest.inspect_glb(path)
    if source.skin_count or source.animation_names:
        raise AssertionError("Source rig or animation leaked into the unrigged GLB")
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in tuple(bpy.data.actions):
        bpy.data.actions.remove(action)
    for armature in tuple(bpy.data.armatures):
        bpy.data.armatures.remove(armature)
    package = REPO_ROOT.name
    context = pipeline.PipelineContext(scene=bpy.context.scene, metadata={
        "glb_input_path": str(path), "glb_normalized_extent": 2.0,
    })
    for module_name, class_name in (("glb_input", "GLBFileInputImplementation"),
                                   ("glb_geometry", "GLBNormalizedGeometryImplementation")):
        implementation = getattr(importlib.import_module(f"{package}.implementations.{module_name}"), class_name)()
        result = implementation.execute(context)
        if not result.success:
            raise AssertionError(f"Unrigged GLB pipeline failed: {result.message}")
        context.set_output(result.stage, result.payload)
    geometry = context.require_output(pipeline.PipelineStage.GEOMETRY)
    assert_unrigged_mesh(geometry.blender_object)
    if bpy.data.armatures or bpy.data.actions:
        raise AssertionError("Source rig data remained available to the fitter")
    return context, geometry.blender_object, normalized_heads, normalized_regions, source


def main() -> None:
    args = arguments()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _, pipeline, rig_module = _package_modules(args.implementation)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    corpus_root = REPO_ROOT / "example" / "v2"
    corpus = json.loads((corpus_root / "manifest.json").read_text())
    asset = next(item for item in corpus["assets"] if item["id"] == args.asset)
    path = corpus_root / asset["file"]
    bpy.context.scene.frame_set(0)
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()), bone_heuristic="TEMPERANCE")
    source_armature = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
    source_armature.data.pose_position = "REST"
    bpy.context.view_layer.update()
    mapping = importlib.import_module(f"{REPO_ROOT.name}.implementations.canonical_motion.mapping")
    resolved = mapping.resolve_source_profile(source_armature.data.bones.keys())
    correspondence = dict(resolved.role_to_bone)
    source_bone_count = len(source_armature.data.bones)
    source_mesh = max(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH" and any(
            mod.type == "ARMATURE" for mod in obj.modifiers
        )),
        key=lambda obj: len(obj.data.vertices),
    )
    reference_heads = {
        bone.name: tuple(source_armature.matrix_world @ bone.head_local)
        for bone in source_armature.data.bones
    }
    source_regions = _source_limb_regions(source_mesh, source_armature, correspondence)
    context, unrigged, reference_heads, reference_regions, unrigged_manifest = _prepare_unrigged_input(
        source_mesh, reference_heads, source_regions, output, pipeline
    )
    z_values = [vertex.co.z for vertex in unrigged.data.vertices]
    height = max(z_values) - min(z_values)
    implementation_class = getattr(
        rig_module, "CanonicalRigV2Implementation", None
    ) or rig_module.CanonicalRigImplementation
    implementation = implementation_class()
    availability = implementation.availability(context)
    if not availability.ready:
        raise AssertionError(f"Real reference biped was rejected: {availability.reason}")
    result = implementation.execute(context)
    if not result.success:
        raise AssertionError(f"Canonical rig failed on {args.asset}: {result.message}")
    rig = result.payload
    if set(rig.armature_object.data.bones.keys()) != EXPECTED_BONES:
        raise AssertionError("Canonical rig produced the wrong bone set")
    candidate_heads = {
        bone.name: tuple(rig.armature_object.matrix_world @ bone.head_local)
        for bone in rig.armature_object.data.bones
    }
    landmarks = landmark_summary(reference_heads, candidate_heads, height,
                                 correspondence=correspondence)
    leg_landmarks = landmark_group_summary(landmarks, LEG_JOINTS)
    weights = skin_weight_summary(_skin_rows(unrigged, rig.armature_object))
    regions, leakage = _limb_region_quality(unrigged, reference_regions)
    pose = _pose_response(unrigged, rig.armature_object, regions)
    leg_pose = _pose_response(unrigged, rig.armature_object, regions, posed_bone="thigh.L", rotation_axis=0)
    poses = pose_quality(unrigged, rig.armature_object, regions)
    hinges = pose_quality(unrigged, rig.armature_object, regions, hinges=True)
    context.set_output(pipeline.PipelineStage.RIG, rig)
    roundtrip = _roundtrip(unrigged, rig.armature_object, output / "canonical_rig.glb", context, reference_regions)
    report = {
        "schema_version": 5,
        "reference_asset": args.asset,
        "input": {"path": str(unrigged_manifest.path), "sha256": unrigged_manifest.sha256,
                  "skin_count": unrigged_manifest.skin_count,
                  "animation_names": unrigged_manifest.animation_names,
                  "source_rig_available_to_fitter": False},
        "rig_implementation": rig.implementation_id,
        "binding_method": rig.binding_method,
        "geometry_warnings": result.metadata["rig_quality"]["warnings"],
        "fit": result.metadata.get("rig_fit"),
        "source_bone_count": source_bone_count,
        "generated_bone_count": len(rig.armature_object.data.bones),
        "acceptance": {
            "max_mean_landmark_error_in_heights": args.max_mean_joint_error,
            "max_landmark_error_in_heights": args.max_joint_error,
            "min_left_pose_displacement": 0.005,
            "max_right_pose_displacement": 0.001,
            "max_mean_arm_unrelated_weight": args.max_arm_unrelated_weight,
            "max_mean_leg_landmark_error_in_heights": args.max_mean_leg_joint_error,
            "max_leg_landmark_error_in_heights": args.max_leg_joint_error,
            "max_mean_leg_unrelated_weight": args.max_leg_unrelated_weight,
            "require_observed_leg_cues": args.require_observed_leg_cues,
            "check_leg_deformation": args.check_leg_deformation,
            "pose_quality": pose_acceptance(args.asset) if args.check_pose_quality else None,
            "hinge_pose_quality": pose_acceptance(args.asset, hinges=True) if args.check_hinge_quality else None,
            "min_left_leg_displacement": .005,
            "max_right_leg_displacement": .001,
        },
        "landmarks": landmarks,
        "lower_body_landmarks": leg_landmarks,
        "skin_weights": weights,
        "arm_region_leakage": {label: value for label,value in leakage.items() if label.startswith("arm")},
        "leg_region_leakage": {label: value for label,value in leakage.items() if label.startswith("leg")},
        "pose_response": pose,
        "leg_pose_response": leg_pose,
        "pose_quality": poses,
        "hinge_pose_quality": hinges,
        "glb_roundtrip": roundtrip,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{rig.implementation_id} mean joint error: {landmarks['mean_error_in_heights']:.4f} heights; "
          f"skin coverage: {weights['weighted_fraction']:.3f}; "
          f"left pose displacement: {pose['left_mean_displacement']:.4f}")
    if args.check_pose_quality:
        for observations in (poses, roundtrip["pose_quality"]):
            check_pose_quality(observations, report["acceptance"]["pose_quality"])
        check_pose_roundtrip(poses, roundtrip["pose_quality"])
    if args.check_hinge_quality:
        for observations in (hinges, roundtrip["hinge_pose_quality"]):
            check_pose_quality(observations, report["acceptance"]["hinge_pose_quality"], expected_count=24)
        check_pose_roundtrip(hinges, roundtrip["hinge_pose_quality"], expected_count=24)
    if weights["weighted_fraction"] < 1.0 or weights["max_influences_per_vertex"] > 4:
        raise AssertionError("Canonical rig skin coverage or influence count regressed")
    if weights["max_weight_sum_error"] > 0.02 or roundtrip["max_weight_sum_error"] > 0.02:
        raise AssertionError("Canonical rig weights are not normalized")
    if roundtrip["weighted_fraction"] < 1.0 or roundtrip["max_influences_per_vertex"] > 4:
        raise AssertionError("Canonical rig GLB lost usable skin weights")
    if pose["left_mean_displacement"] <= report["acceptance"]["min_left_pose_displacement"]:
        raise AssertionError("Canonical rig GLB or pose response regressed")
    if pose["right_mean_displacement"] > report["acceptance"]["max_right_pose_displacement"]:
        raise AssertionError("Canonical rig pose deformed the opposite arm")
    imported_pose = roundtrip["pose_response"]
    if imported_pose["left_mean_displacement"] <= report["acceptance"]["min_left_pose_displacement"] or imported_pose["right_mean_displacement"] > report["acceptance"]["max_right_pose_displacement"]:
        raise AssertionError("Canonical rig reimport lost localized pose deformation")
    for category, limit in (("arm",args.max_arm_unrelated_weight),("leg",args.max_leg_unrelated_weight)):
        for observations in (report[f"{category}_region_leakage"], roundtrip[f"{category}_region_leakage"]):
            if any(region["mean_unrelated_weight"] > limit for region in observations.values()):
                raise AssertionError(f"Canonical rig {category} weights leaked into unrelated regions")
    if args.check_leg_deformation:
        for response in (leg_pose,roundtrip["leg_pose_response"]):
            if response["left_mean_displacement"] <= .005 or response["right_mean_displacement"] > .001:
                raise AssertionError("Canonical rig lost localized leg deformation")
    if leg_landmarks["mean_error_in_heights"] > args.max_mean_leg_joint_error or leg_landmarks["max_error_in_heights"] > args.max_leg_joint_error:
        raise AssertionError("Canonical rig leg placement diverged from reference joints")
    if args.require_observed_leg_cues:
        evidence = (report["fit"] or {}).get("lower_body",{}).get("legs",{})
        if any(evidence.get(side,{}).get("hip_method") != "observed-knee-ankle-length-prior" for side in ("L","R")):
            raise AssertionError("Canonical rig did not observe bilateral knee/ankle cues")
    if landmarks["mean_error_in_heights"] > report["acceptance"]["max_mean_landmark_error_in_heights"] or landmarks["max_error_in_heights"] > report["acceptance"]["max_landmark_error_in_heights"]:
        raise AssertionError("Canonical rig bone placement diverged from reference joints")


if __name__ == "__main__":
    main()
