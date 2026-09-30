"""Functional Canonical Motion smoke test using the pinned GLB fixtures.

The successful case strips RiggedFigure down to an unrigged mesh, creates a
Canonical Biped V2 target, retargets the original external GLB animation, and
checks the exported/reimported animated GLB.  RiggedSimple is deliberately not
a supported source profile and must fail without mutating the target rig.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
import traceback
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BONES = {
    "root", "pelvis", "spine", "chest", "neck", "head",
    *(f"{part}.{side}" for side in ("L", "R") for part in (
        "upper_arm", "forearm", "hand", "thigh", "shin", "foot"
    )),
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--asset-root", type=Path, default=REPO_ROOT / "example" / "v2" / "assets")
    parser.add_argument("--output", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return parser.parse_args(argv)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _import_package(package_root: Path) -> str:
    root = package_root.resolve()
    _require((root / "__init__.py").is_file(), f"Invalid package root: {root}")
    if str(root.parent) not in sys.path:
        sys.path.insert(0, str(root.parent))
    importlib.import_module(root.name)
    return root.name


def _clear_scene() -> None:
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for action in tuple(bpy.data.actions):
        bpy.data.actions.remove(action)
    for collection in (bpy.data.armatures, bpy.data.meshes):
        for block in tuple(collection):
            if block.users == 0:
                collection.remove(block)


def _unrigged_world_mesh(source: bpy.types.Object) -> bpy.types.Object:
    vertices = [tuple(source.matrix_world @ vertex.co) for vertex in source.data.vertices]
    faces = [tuple(polygon.vertices) for polygon in source.data.polygons]
    mesh = bpy.data.meshes.new("MotionSmokeTargetMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("MotionSmokeTarget", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _remove_imported_source(imported: tuple[bpy.types.Object, ...]) -> None:
    for obj in imported:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for action in tuple(bpy.data.actions):
        if action.users == 0:
            bpy.data.actions.remove(action)
    for collection in (bpy.data.armatures, bpy.data.meshes):
        for block in tuple(collection):
            if block.users == 0:
                collection.remove(block)


def _build_target(package_name: str, reference_path: Path):
    _clear_scene()
    before = {obj.as_pointer() for obj in bpy.data.objects}
    result = bpy.ops.import_scene.gltf(filepath=str(reference_path.resolve()))
    _require("FINISHED" in result, "Could not import RiggedFigure geometry fixture")
    imported = tuple(obj for obj in bpy.data.objects if obj.as_pointer() not in before)
    source_mesh = max(
        (obj for obj in imported if obj.type == "MESH" and any(
            modifier.type == "ARMATURE" for modifier in obj.modifiers
        )),
        key=lambda obj: len(obj.data.vertices),
    )
    target_mesh = _unrigged_world_mesh(source_mesh)
    _remove_imported_source(imported)
    _require(target_mesh.parent is None and not target_mesh.vertex_groups,
             "Target geometry retained source rig data")

    geometry_contracts = importlib.import_module(f"{package_name}.core.geometry_contracts")
    pipeline = importlib.import_module(f"{package_name}.core.pipeline_contracts")
    rig_module = importlib.import_module(f"{package_name}.implementations.canonical_rig_v2")
    context = pipeline.PipelineContext(scene=bpy.context.scene)
    geometry = geometry_contracts.GeometrySurfaceOutput(
        blender_object=target_mesh,
        source=object(),
        projection_space=geometry_contracts.GeometryProjectionSpace(32, 32, 32),
        implementation_id="motion-smoke-reference-mesh",
    )
    context.set_output(pipeline.PipelineStage.GEOMETRY, geometry)
    rig_impl = rig_module.CanonicalRigV2Implementation()
    availability = rig_impl.availability(context)
    _require(availability.ready, f"Canonical Biped V2 unavailable: {availability.reason}")
    rig_result = rig_impl.execute(context)
    _require(rig_result.success, f"Canonical Biped V2 failed: {rig_result.message}")
    context.set_output(pipeline.PipelineStage.RIG, rig_result.payload)
    return context, pipeline, rig_result.payload, target_mesh


def _evaluated_positions(obj: bpy.types.Object) -> tuple[tuple[float, float, float], ...]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return tuple(tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


def _sample_frames(frame_start: int, frame_end: int, count: int = 9) -> tuple[int, ...]:
    # Keep a fixed sample count and integer rounding so the smoke is reproducible.
    if frame_end <= frame_start:
        return (frame_start,)
    values = {
        round(frame_start + (frame_end - frame_start) * index / (count - 1))
        for index in range(count)
    }
    return tuple(sorted(values))


def _animation_response(
    mesh: bpy.types.Object,
    armature: bpy.types.Object,
    action: bpy.types.Action,
    frame_start: int,
    frame_end: int,
) -> dict[str, float | int]:
    animation = armature.animation_data_create()
    animation.use_nla = False
    animation.action = action
    frames = _sample_frames(frame_start, frame_end)
    scene = bpy.context.scene
    scene.frame_set(frames[0])
    bpy.context.view_layer.update()
    baseline_vertices = _evaluated_positions(mesh)
    baseline_bones = {
        bone.name: tuple(value for row in bone.matrix for value in row)
        for bone in armature.pose.bones if bone.name != "root"
    }
    z_values = [point[2] for point in baseline_vertices]
    height = max(z_values) - min(z_values)
    max_displacement = 0.0
    max_bone_delta = 0.0
    for frame in frames[1:]:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        posed = _evaluated_positions(mesh)
        _require(len(posed) == len(baseline_vertices), "Animation changed mesh topology")
        max_displacement = max(
            max_displacement,
            max(math.dist(before, after) for before, after in zip(baseline_vertices, posed)),
        )
        for bone in armature.pose.bones:
            if bone.name == "root":
                continue
            values = tuple(value for row in bone.matrix for value in row)
            max_bone_delta = max(
                max_bone_delta,
                max(abs(a - b) for a, b in zip(baseline_bones[bone.name], values)),
            )
    scene.frame_set(frames[0])
    bpy.context.view_layer.update()
    _require(max_bone_delta > 1e-4, "Retargeted action is constant across sampled frames")
    _require(height > 0.0 and max_displacement / height > 0.005,
             "Retargeted action did not visibly deform the target mesh")
    return {
        "sample_count": len(frames),
        "max_bone_matrix_delta": max_bone_delta,
        "max_vertex_displacement": max_displacement,
        "max_displacement_in_heights": max_displacement / height,
    }


def _animated_roundtrip(
    path: Path,
) -> dict[str, object]:
    _require(path.is_file() and path.stat().st_size > 0,
             "Pipeline EXPORT did not publish an animated GLB")

    object_pointers = {obj.as_pointer() for obj in bpy.data.objects}
    actions_before = set(bpy.data.actions)
    result = bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    _require("FINISHED" in result, "Animated Motion GLB reimport failed")
    imported = [obj for obj in bpy.data.objects if obj.as_pointer() not in object_pointers]
    imported_actions = tuple(action for action in bpy.data.actions if action not in actions_before)
    imported_armatures = [obj for obj in imported if obj.type == "ARMATURE"]
    imported_meshes = [obj for obj in imported if obj.type == "MESH"]
    _require(len(imported_armatures) == 1 and imported_meshes,
             "Animated Motion GLB lost its armature or mesh")
    imported_armature = imported_armatures[0]
    _require(set(imported_armature.data.bones.keys()) == EXPECTED_BONES,
             "Animated Motion GLB changed the canonical bone set")
    bound = [obj for obj in imported_meshes if any(
        modifier.type == "ARMATURE" and modifier.object is imported_armature
        for modifier in obj.modifiers
    )]
    _require(len(bound) == 1, "Animated Motion GLB lost its skin binding")
    _require(imported_actions, "Animated Motion GLB lost every animation action")
    imported_action = (
        imported_armature.animation_data.action
        if imported_armature.animation_data is not None
        and imported_armature.animation_data.action is not None
        else imported_actions[0]
    )
    imported_start = math.floor(float(imported_action.frame_range[0]))
    imported_end = math.ceil(float(imported_action.frame_range[1]))
    _require(imported_end > imported_start, "Imported Motion action has no duration")
    response = _animation_response(
        bound[0], imported_armature, imported_action, imported_start, imported_end
    )
    return {
        "glb_bytes": path.stat().st_size,
        "animation_count": len(imported_actions),
        "action_names": sorted(item.name for item in imported_actions),
        "frame_start": imported_start,
        "frame_end": imported_end,
        **response,
    }


def _success_case(package_name: str, source_path: Path, output: Path) -> dict[str, object]:
    context, pipeline, rig, mesh = _build_target(package_name, source_path)
    motion_module = importlib.import_module(f"{package_name}.implementations.canonical_motion")
    motion_contracts = importlib.import_module(f"{package_name}.core.motion_contracts")
    context.metadata["motion_source_path"] = str(source_path.resolve())
    implementation = motion_module.CanonicalMotionRetargetImplementation()
    availability = implementation.availability(context)
    _require(availability.ready, f"Canonical Motion unavailable: {availability.reason}")
    result = implementation.execute(context)
    _require(result.success, f"Canonical Motion failed: {result.message}")
    _require(result.stage == pipeline.PipelineStage.MOTION, "Incorrect Motion result stage")
    _require(result.implementation_id == "canonical-motion-retarget-v1",
             "Incorrect Motion implementation ID")
    motion = result.payload
    _require(isinstance(motion, motion_contracts.MotionOutput),
             "Motion result did not return MotionOutput")
    _require(motion.rig is rig and motion.armature_object is rig.armature_object,
             "Motion output lost its target rig")
    _require(motion.clips, "Motion output contains no clips")
    _require(len(motion.source_bone_map) == 17 and "root" not in motion.source_bone_map,
             "Motion output has an invalid semantic source mapping")
    root_mode = getattr(motion.root_motion_mode, "value", motion.root_motion_mode)
    _require(str(root_mode).upper().replace("-", "_") == "IN_PLACE",
             "Canonical Motion did not keep root motion in place")

    clip = motion.clips[0]
    _require(clip.frame_end > clip.frame_start and clip.fps > 0.0,
             "Motion clip has invalid frames or FPS")
    _require(len(clip.animated_roles) == 17 and "root" not in clip.animated_roles,
             "Motion clip does not animate the complete canonical role set")
    duration = (clip.frame_end - clip.frame_start) / clip.fps
    _require(duration > 0.0, "Motion clip duration is not positive")
    action_start, action_end = (float(value) for value in clip.action.frame_range)
    _require(action_start <= clip.frame_start and action_end >= clip.frame_end,
             "Motion clip frames disagree with its Blender action")
    response = _animation_response(
        mesh, rig.armature_object, clip.action, clip.frame_start, clip.frame_end
    )
    second_action = clip.action.copy()
    second_action.name = f"{clip.action.name}_ExportVariant"
    second_action.use_fake_user = True
    second_clip = motion_contracts.MotionClipOutput(
        name=f"{clip.name}_ExportVariant",
        action=second_action,
        frame_start=clip.frame_start,
        frame_end=clip.frame_end,
        fps=clip.fps,
        animated_roles=clip.animated_roles,
        metadata={"purpose": "multi-clip-export-smoke"},
    )
    export_motion = motion_contracts.MotionOutput(
        rig=motion.rig,
        armature_object=motion.armature_object,
        implementation_id=motion.implementation_id,
        clips=(clip, second_clip),
        source_bone_map=motion.source_bone_map,
        root_motion_mode=motion.root_motion_mode,
        metrics=motion.metrics,
        metadata=motion.metadata,
    )
    decoy_action = clip.action.copy()
    decoy_action.name = "Meshvenn_Decoy_Action"
    decoy_action.use_fake_user = True
    context.set_output(pipeline.PipelineStage.MOTION, export_motion)
    export_path = output / "canonical_motion.glb"
    context.metadata["export_output_path"] = str(export_path)
    context.metadata["export_overwrite_existing"] = True
    export_module = importlib.import_module(f"{package_name}.implementations.glb_export")
    export_contracts = importlib.import_module(f"{package_name}.core.export_contracts")
    export_implementation = export_module.GLBExportImplementation()
    export_availability = export_implementation.availability(context)
    _require(export_availability.ready,
             f"Pipeline EXPORT unavailable: {export_availability.reason}")
    export_result = export_implementation.execute(context)
    _require(export_result.success, f"Pipeline EXPORT failed: {export_result.message}")
    exported = export_result.payload
    _require(isinstance(exported, export_contracts.ExportOutput),
             "Pipeline EXPORT did not return ExportOutput")
    _require(exported.geometry is rig.geometry and exported.rig is rig
             and exported.motion is export_motion,
             "Pipeline EXPORT lost Geometry/Rig/Motion provenance")
    _require(len(exported.sha256) == 64 and exported.size_bytes > 0,
             "Pipeline EXPORT did not publish integrity metadata")
    _require(len(exported.animation_names) == 2,
             "Pipeline EXPORT did not preserve both Motion clips")
    _require(all("Decoy" not in name for name in exported.animation_names),
             "Pipeline EXPORT leaked an action outside MotionOutput")
    roundtrip = _animated_roundtrip(exported.path)
    return {
        "implementation": motion.implementation_id,
        "clip_count": len(motion.clips),
        "clip_name": clip.name,
        "frame_start": clip.frame_start,
        "frame_end": clip.frame_end,
        "fps": clip.fps,
        "duration_seconds": duration,
        "animated_role_count": len(clip.animated_roles),
        "response": response,
        "export": {
            "implementation_id": exported.implementation_id,
            "size_bytes": exported.size_bytes,
            "sha256": exported.sha256,
            "animation_names": exported.animation_names,
        },
        "glb_roundtrip": roundtrip,
    }


def _rejection_case(package_name: str, target_reference: Path, unsupported: Path) -> dict[str, object]:
    context, pipeline, rig, _ = _build_target(package_name, target_reference)
    motion_module = importlib.import_module(f"{package_name}.implementations.canonical_motion")
    context.metadata["motion_source_path"] = str(unsupported.resolve())
    implementation = motion_module.CanonicalMotionRetargetImplementation()
    actions_before = set(bpy.data.actions)
    result = implementation.execute(context)
    _require(result.stage == pipeline.PipelineStage.MOTION and result.failed,
             "RiggedSimple must be rejected by Canonical Motion")
    _require(result.message, "RiggedSimple rejection needs an explanation")
    target_animation = rig.armature_object.animation_data
    _require(target_animation is None or target_animation.action is None,
             "Rejected source left an action on the target armature")
    _require(set(bpy.data.actions) == actions_before,
             "Rejected source leaked imported or partially baked actions")
    _require(context.get_output(pipeline.PipelineStage.MOTION) is None,
             "Rejected source published a Motion output")
    return {"source": unsupported.name, "message": result.message}


def main() -> None:
    args = _arguments()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    package_name = _import_package(args.package_root)
    rigged_figure = args.asset_root.resolve() / "RiggedFigure.glb"
    rigged_simple = args.asset_root.resolve() / "RiggedSimple.glb"
    _require(rigged_figure.is_file() and rigged_simple.is_file(),
             "Pinned Motion GLB fixtures are missing")
    success = _success_case(package_name, rigged_figure, output)
    rejection = _rejection_case(package_name, rigged_figure, rigged_simple)
    report = {
        "schema_version": 1,
        "source_asset": "RiggedFigure.glb",
        "unsupported_asset": "RiggedSimple.glb",
        "motion": success,
        "rejection": rejection,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    print(
        "Canonical Motion Blender smoke: PASS; "
        f"clip={success['clip_name']}; frames={success['frame_start']}-{success['frame_end']}; "
        f"duration={success['duration_seconds']:.3f}s; "
        f"deformation={success['response']['max_displacement_in_heights']:.4f}H"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
