"""Functional Canonical Rig smoke test for a packaged Meshvenn extension.

Run with::

    blender --background --python tests/blender_rig_smoke.py -- \
        --package-root dist/blender_projection_tool
"""

from __future__ import annotations

import argparse
import importlib
import math
import sys
import tempfile
import traceback
from pathlib import Path

import bpy


EXPECTED_BONES = {
    "root", "pelvis", "spine", "chest", "neck", "head",
    *(f"{part}.{side}" for side in ("L", "R") for part in (
        "upper_arm", "forearm", "hand", "thigh", "shin", "foot"
    )),
}


def _arguments():
    parser = argparse.ArgumentParser(description="Smoke-test the packaged Canonical Rig.")
    parser.add_argument("--package-root", default="dist/blender_projection_tool")
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _import_package(package_root: Path):
    package_root = package_root.resolve()
    _require(package_root.is_dir(), f"Package root does not exist: {package_root}")
    for relative in (
        "__init__.py", "core/canonical_rig.py", "core/rig_contracts.py",
        "implementations/canonical_rig/__init__.py",
        "implementations/canonical_rig/implementation.py",
    ):
        _require((package_root / relative).is_file(), f"Missing packaged file: {relative}")
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    package_name = package_root.name
    importlib.import_module(package_name)
    return package_name


def _add_box(vertices, faces, x_min, x_max, y_min, y_max, z_min, z_max):
    offset = len(vertices)
    vertices.extend((
        (x_min, y_min, z_min), (x_max, y_min, z_min),
        (x_max, y_max, z_min), (x_min, y_max, z_min),
        (x_min, y_min, z_max), (x_max, y_min, z_max),
        (x_max, y_max, z_max), (x_min, y_max, z_max),
    ))
    faces.extend(tuple(offset + index for index in face) for face in (
        (0, 3, 2, 1), (4, 5, 6, 7),
        (0, 1, 5, 4), (1, 2, 6, 5),
        (2, 3, 7, 6), (3, 0, 4, 7),
    ))


def _create_biped_mesh():
    vertices, faces = [], []
    _add_box(vertices, faces, -.22, .22, -.11, .11, .68, 1.62)
    _add_box(vertices, faces, -.15, .15, -.1, .1, 1.62, 2.0)
    for side in (-1, 1):
        x_min, x_max = (-.75, -.2) if side < 0 else (.2, .75)
        _add_box(vertices, faces, x_min, x_max, -.075, .075, 1.2, 1.46)
        x_min, x_max = (-.2, -.025) if side < 0 else (.025, .2)
        _add_box(vertices, faces, x_min, x_max, -.085, .085, 0.0, .74)
    mesh = bpy.data.meshes.new("MeshvennRigSmokeMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("MeshvennRigSmokeBiped", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _create_empty_mesh():
    mesh = bpy.data.meshes.new("MeshvennRigSmokeEmptyMesh")
    obj = bpy.data.objects.new("MeshvennRigSmokeEmpty", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _geometry_output(package_name: str, obj):
    contracts = importlib.import_module(f"{package_name}.core.geometry_contracts")
    return contracts.GeometrySurfaceOutput(
        blender_object=obj,
        source=object(),
        projection_space=contracts.GeometryProjectionSpace(20, 10, 20, voxel_size=.1),
        implementation_id="rig-smoke-geometry",
    )


def _context(package_name: str, obj):
    pipeline = importlib.import_module(f"{package_name}.core.pipeline_contracts")
    context = pipeline.PipelineContext(scene=bpy.context.scene)
    geometry = _geometry_output(package_name, obj)
    context.set_output(pipeline.PipelineStage.GEOMETRY, geometry)
    return context, geometry, pipeline


def _evaluated_positions(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return tuple(tuple(vertex.co) for vertex in mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


def _check_success(package_name: str, implementation):
    rig_contracts = importlib.import_module(f"{package_name}.core.rig_contracts")
    obj = _create_biped_mesh()
    obj.location = (2.0, -3.0, 0.5)
    obj.rotation_euler[2] = math.radians(20)
    obj.scale = (1.1, 1.1, 1.1)
    bpy.context.view_layer.update()
    initial_world = obj.matrix_world.copy()
    context, geometry, pipeline = _context(package_name, obj)
    result = implementation.execute(context)
    _require(result.success, f"Rig stage failed: {result.message}")
    _require(result.stage == pipeline.PipelineStage.RIG, "Incorrect result stage")
    _require(result.implementation_id == "canonical-biped-v1", "Incorrect implementation ID")
    rig = result.payload
    _require(isinstance(rig, rig_contracts.RigOutput), "Result payload is not RigOutput")
    _require((rig.schema_version, rig.up_axis, rig.forward_axis) == (1, "Z", "-Y"), "Rig axes or schema changed")
    _require(rig.geometry is geometry and rig.blender_object is obj, "Output lost source mesh")

    _require(all(abs(a - b) < 1e-5 for row_a, row_b in zip(initial_world, obj.matrix_world)
                 for a, b in zip(row_a, row_b)), "Rigging changed the mesh world transform")
    armature = rig.armature_object
    _require(armature.type == "ARMATURE", "Rig output is not a Blender armature")
    _require(len(armature.data.bones) == 18, "Canonical rig must contain 18 bones")
    actual_bones = set(armature.data.bones.keys())
    _require(actual_bones == EXPECTED_BONES, f"Unexpected bone names: {actual_bones ^ EXPECTED_BONES}")
    _require(set(rig.semantic_bones.values()) == EXPECTED_BONES, "Semantic bone map is incomplete")
    _require(all(role and name for role, name in rig.semantic_bones.items()), "Empty semantic role")
    _require(rig.binding_method in {"blender-bone-heat", "canonical-distance"}, "Unknown binding method")
    _require(any(
        modifier.type == "ARMATURE" and modifier.object is armature
        for modifier in obj.modifiers
    ), "Mesh lacks an Armature modifier")

    deform_groups = {
        group.index for group in obj.vertex_groups
        if group.name in EXPECTED_BONES and group.name != "root"
    }
    _require(len(deform_groups) == 17, "Missing deforming vertex groups")
    for vertex in obj.data.vertices:
        weights = [
            member.weight for member in vertex.groups
            if member.group in deform_groups and member.weight > 0
        ]
        _require(weights, f"Vertex {vertex.index} is not skinned")
        _require(len(weights) <= 4, f"Vertex {vertex.index} has too many bone influences")
        _require(abs(sum(weights) - 1.0) < .02, f"Vertex {vertex.index} weights are not normalized")

    rest = _evaluated_positions(obj)
    pose_bone = armature.pose.bones["upper_arm.R"]
    pose_bone.rotation_mode = "XYZ"
    pose_bone.rotation_euler[1] = math.radians(35)
    bpy.context.view_layer.update()
    posed = _evaluated_positions(obj)
    _require(len(rest) == len(posed), "Pose changed mesh topology")
    displacement = max(math.dist(a, b) for a, b in zip(rest, posed))
    _require(displacement > .005, f"Pose did not deform mesh (maximum displacement {displacement})")
    pose_bone.rotation_euler[1] = 0.0
    bpy.context.view_layer.update()
    _check_glb_roundtrip(obj, armature)
    print(f"Rig OK: {len(actual_bones)} bones, {len(rest)} skinned vertices, {displacement:.4f} pose displacement")


def _check_glb_roundtrip(mesh, armature) -> None:
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    mesh.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    before = {obj.as_pointer() for obj in bpy.data.objects}
    with tempfile.TemporaryDirectory(prefix="meshvenn-rig-") as temporary:
        path = str(Path(temporary) / "canonical-biped.glb")
        result = bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
        _require("FINISHED" in result and Path(path).stat().st_size > 0, "GLB export failed")
        result = bpy.ops.import_scene.gltf(filepath=path)
        _require("FINISHED" in result, "GLB import failed")
    imported = [obj for obj in bpy.data.objects if obj.as_pointer() not in before]
    imported_arms = [obj for obj in imported if obj.type == "ARMATURE"]
    imported_meshes = [obj for obj in imported if obj.type == "MESH"]
    _require(imported_arms and imported_meshes, "GLB lost its mesh or armature")
    _require(any(
        modifier.type == "ARMATURE" and modifier.object in imported_arms
        for obj in imported_meshes for modifier in obj.modifiers
    ), "GLB lost the skin binding")
    print("GLB export/import preserved armature and skin binding")


def _check_invalid_mesh(package_name: str, implementation):
    obj = _create_empty_mesh()
    context, _, pipeline = _context(package_name, obj)
    before = {item.name for item in bpy.data.objects if item.type == "ARMATURE"}
    try:
        result = implementation.execute(context)
    except (ValueError, RuntimeError, TypeError) as exc:
        _require(str(exc), "Invalid mesh raised an empty error")
    else:
        _require(result.stage == pipeline.PipelineStage.RIG and result.failed,
                 "Empty mesh must return a failed RIG result")
        _require(result.message, "Failed RIG result needs an explanation")
    after = {item.name for item in bpy.data.objects if item.type == "ARMATURE"}
    _require(after == before, "Invalid mesh leaked an armature")
    _require(not obj.modifiers and not obj.vertex_groups, "Invalid mesh was partially bound")
    print("Invalid mesh rejected without Blender data leaks")


def _cleanup(initial_objects, initial_meshes, initial_armatures):
    for obj in tuple(bpy.data.objects):
        if obj.as_pointer() not in initial_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in tuple(bpy.data.meshes):
        if mesh.as_pointer() not in initial_meshes and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for armature in tuple(bpy.data.armatures):
        if armature.as_pointer() not in initial_armatures and armature.users == 0:
            bpy.data.armatures.remove(armature)


def main() -> None:
    args = _arguments()
    initial_objects = {obj.as_pointer() for obj in bpy.data.objects}
    initial_meshes = {mesh.as_pointer() for mesh in bpy.data.meshes}
    initial_armatures = {armature.as_pointer() for armature in bpy.data.armatures}
    try:
        package_name = _import_package(Path(args.package_root))
        implementation_module = importlib.import_module(
            f"{package_name}.implementations.canonical_rig"
        )
        implementation = implementation_module.CanonicalRigImplementation()
        _check_success(package_name, implementation)
        _check_invalid_mesh(package_name, implementation)
        print("Canonical Rig Blender smoke: PASS")
    finally:
        _cleanup(initial_objects, initial_meshes, initial_armatures)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
