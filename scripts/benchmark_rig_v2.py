"""Benchmark Canonical Rig V1 against RiggedFigure's real source skeleton.

The source armature is used only for scoring. MeshVenn receives a new,
world-space, unrigged copy of the reference mesh as its GEOMETRY output.
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

from scripts.glb_v2_rig_metrics import landmark_summary, skin_weight_summary


EXPECTED_BONES = {
    "root", "pelvis", "spine", "chest", "neck", "head",
    *(f"{part}.{side}" for side in ("L", "R") for part in (
        "upper_arm", "forearm", "hand", "thigh", "shin", "foot"
    )),
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def _package_modules():
    package_name = REPO_ROOT.name
    importlib.import_module(package_name)
    return (
        importlib.import_module(f"{package_name}.core.geometry_contracts"),
        importlib.import_module(f"{package_name}.core.pipeline_contracts"),
        importlib.import_module(f"{package_name}.implementations.canonical_rig"),
    )


def _unrigged_world_mesh(source: bpy.types.Object) -> bpy.types.Object:
    vertices = [tuple(source.matrix_world @ vertex.co) for vertex in source.data.vertices]
    faces = [tuple(polygon.vertices) for polygon in source.data.polygons]
    mesh = bpy.data.meshes.new("V2_RiggedFigure_UnriggedMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("V2_RiggedFigure_Unrigged", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _evaluated_positions(obj: bpy.types.Object) -> tuple[tuple[float, float, float], ...]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return tuple(tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


def _skin_rows(mesh: bpy.types.Object, armature: bpy.types.Object) -> list[list[float]]:
    deform = {bone.name for bone in armature.data.bones if bone.use_deform}
    indices = {group.index for group in mesh.vertex_groups if group.name in deform}
    return [
        [member.weight for member in vertex.groups if member.group in indices]
        for vertex in mesh.data.vertices
    ]


def _pose_response(mesh: bpy.types.Object, armature: bpy.types.Object) -> dict:
    rest = _evaluated_positions(mesh)
    bone = armature.pose.bones["upper_arm.L"]
    bone.rotation_mode = "XYZ"
    bone.rotation_euler[1] = math.radians(35)
    bpy.context.view_layer.update()
    posed = _evaluated_positions(mesh)
    bone.rotation_euler[1] = 0.0
    bpy.context.view_layer.update()
    if len(rest) != len(posed):
        raise AssertionError("Pose changed mesh topology")
    left = [math.dist(before, after) for before, after in zip(rest, posed) if before[0] > 0.10]
    right = [math.dist(before, after) for before, after in zip(rest, posed) if before[0] < -0.10]
    if not left or not right:
        raise AssertionError("Reference figure lacks bilateral pose samples")
    return {
        "posed_bone": "upper_arm.L",
        "angle_degrees": 35,
        "left_mean_displacement": sum(left) / len(left),
        "right_mean_displacement": sum(right) / len(right),
        "left_max_displacement": max(left),
        "right_max_displacement": max(right),
    }


def _roundtrip(mesh: bpy.types.Object, armature: bpy.types.Object, path: Path) -> dict:
    for selected in tuple(bpy.context.selected_objects):
        selected.select_set(False)
    mesh.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    result = bpy.ops.export_scene.gltf(filepath=str(path.resolve()), export_format="GLB", use_selection=True)
    if "FINISHED" not in result or not path.is_file():
        raise AssertionError("Canonical rig GLB export failed")
    before = {obj.as_pointer() for obj in bpy.data.objects}
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
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
    return {"glb_bytes": path.stat().st_size, "bone_count": len(arms[0].data.bones), **weights}


def main() -> None:
    output = arguments().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    geometry_contracts, pipeline, rig_module = _package_modules()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    path = REPO_ROOT / "example" / "v2" / "assets" / "RiggedFigure.glb"
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    source_armature = next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")
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
    unrigged = _unrigged_world_mesh(source_mesh)
    z_values = [vertex.co.z for vertex in unrigged.data.vertices]
    height = max(z_values) - min(z_values)
    context = pipeline.PipelineContext(scene=bpy.context.scene)
    geometry = geometry_contracts.GeometrySurfaceOutput(
        blender_object=unrigged, source=object(),
        projection_space=geometry_contracts.GeometryProjectionSpace(32, 32, 32),
        implementation_id="glb-v2-reference-mesh",
    )
    context.set_output(pipeline.PipelineStage.GEOMETRY, geometry)
    implementation = rig_module.CanonicalRigImplementation()
    availability = implementation.availability(context)
    if not availability.ready:
        raise AssertionError(f"Real reference biped was rejected: {availability.reason}")
    result = implementation.execute(context)
    if not result.success:
        raise AssertionError(f"Canonical Rig V1 failed on RiggedFigure: {result.message}")
    rig = result.payload
    if set(rig.armature_object.data.bones.keys()) != EXPECTED_BONES:
        raise AssertionError("Canonical Rig V1 produced the wrong bone set")
    candidate_heads = {
        bone.name: tuple(rig.armature_object.matrix_world @ bone.head_local)
        for bone in rig.armature_object.data.bones
    }
    landmarks = landmark_summary(reference_heads, candidate_heads, height)
    weights = skin_weight_summary(_skin_rows(unrigged, rig.armature_object))
    pose = _pose_response(unrigged, rig.armature_object)
    roundtrip = _roundtrip(unrigged, rig.armature_object, output / "canonical_rig.glb")
    report = {
        "schema_version": 1,
        "reference_asset": "rigged_figure",
        "rig_implementation": rig.implementation_id,
        "binding_method": rig.binding_method,
        "geometry_warnings": result.metadata["rig_quality"]["warnings"],
        "source_bone_count": len(source_armature.data.bones),
        "generated_bone_count": len(rig.armature_object.data.bones),
        "acceptance": {
            "max_mean_landmark_error_in_heights": 0.15,
            "max_landmark_error_in_heights": 0.20,
            "min_left_pose_displacement": 0.005,
            "max_right_pose_displacement": 0.001,
        },
        "landmarks": landmarks,
        "skin_weights": weights,
        "pose_response": pose,
        "glb_roundtrip": roundtrip,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"V2 rig mean joint error: {landmarks['mean_error_in_heights']:.4f} heights; "
          f"skin coverage: {weights['weighted_fraction']:.3f}; "
          f"left pose displacement: {pose['left_mean_displacement']:.4f}")
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
    if landmarks["mean_error_in_heights"] > report["acceptance"]["max_mean_landmark_error_in_heights"] or landmarks["max_error_in_heights"] > report["acceptance"]["max_landmark_error_in_heights"]:
        raise AssertionError("Canonical rig bone placement diverged from reference joints")


if __name__ == "__main__":
    main()
