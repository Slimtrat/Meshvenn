"""Run GLB -> preserved Geometry/Rig/Motion -> validated GLB export."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-profile", required=True)
    parser.add_argument("--expected-archetype", required=True)
    parser.add_argument("--expected-animations", type=int, required=True)
    parser.add_argument("--unsupported-input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
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
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in (
        bpy.data.actions,
        bpy.data.armatures,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.images,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in tuple(collection):
            if block.users == 0:
                collection.remove(block)


def _world_dimensions(meshes) -> tuple[float, float, float]:
    points = tuple(
        mesh.matrix_world @ Vector(corner)
        for mesh in meshes
        for corner in mesh.bound_box
    )
    return tuple(
        max(point[index] for point in points)
        - min(point[index] for point in points)
        for index in range(3)
    )


def _clip_pose_span(armature: bpy.types.Object, clip) -> float:
    animation = armature.animation_data_create()
    previous_action = animation.action
    previous_use_nla = animation.use_nla
    previous_frame = bpy.context.scene.frame_current
    start = int(clip.frame_start)
    end = int(clip.frame_end)
    frames = sorted({round(start + (end - start) * index / 4) for index in range(5)})
    try:
        animation.use_nla = False
        animation.action = clip.action
        bpy.context.scene.frame_set(frames[0])
        bpy.context.view_layer.update()
        baseline = {
            bone.name: tuple(float(value) for row in bone.matrix for value in row)
            for bone in armature.pose.bones
        }
        largest = 0.0
        for frame in frames[1:]:
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            for bone in armature.pose.bones:
                current = tuple(float(value) for row in bone.matrix for value in row)
                largest = max(
                    largest,
                    max(
                        abs(left - right)
                        for left, right in zip(baseline[bone.name], current)
                    ),
                )
        return largest
    finally:
        animation.action = previous_action
        animation.use_nla = previous_use_nla
        bpy.context.scene.frame_set(previous_frame)
        bpy.context.view_layer.update()


def main() -> None:
    args = _arguments()
    source_path = args.input.resolve(strict=True)
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    export_path = output_root / "preserved-character.glb"
    export_path.unlink(missing_ok=True)

    package_name = _import_package(args.package_root)
    pipeline = importlib.import_module(f"{package_name}.core.pipeline_contracts")
    runner_module = importlib.import_module(f"{package_name}.core.pipeline_runner")
    registry_module = importlib.import_module(f"{package_name}.core.pipeline_registry")
    score_module = importlib.import_module(f"{package_name}.core.glb_pipeline_score")
    glb_input = importlib.import_module(f"{package_name}.implementations.glb_input")
    preservation = importlib.import_module(
        f"{package_name}.implementations.glb_preservation"
    )
    glb_export = importlib.import_module(f"{package_name}.implementations.glb_export")
    manifest_module = importlib.import_module(
        f"{package_name}.implementations.glb_export.manifest"
    )

    _clear_scene()
    registry = registry_module.PipelineRegistry()
    implementations = (
        glb_input.GLBFileInputImplementation(),
        preservation.GLBPreservedGeometryImplementation(),
        preservation.GLBSourceRigImplementation(),
        preservation.GLBSourceMotionImplementation(),
        glb_export.GLBExportImplementation(),
    )
    for implementation in implementations:
        registry.register(implementation)
    selections = tuple(
        pipeline.PipelineStageSelection(
            implementation.descriptor.stage,
            implementation.descriptor.identifier,
        )
        for implementation in implementations
    )
    context = pipeline.PipelineContext(
        scene=bpy.context.scene,
        metadata={
            "source": "glb-preservation-smoke",
            "glb_input_path": str(source_path),
            "glb_normalized_extent": 2.0,
            "export_output_path": str(export_path),
            "export_overwrite_existing": False,
        },
    )
    runner = runner_module.PipelineRunner(registry)
    preparation_report = runner.run(
        pipeline.PipelinePlan(selections=selections[:2]), context
    )
    if not preparation_report.success:
        details = [record.result.message for record in preparation_report.records]
        details.extend(issue.message for issue in preparation_report.issues)
        raise AssertionError(
            "Preserved GLB preparation failed: " + " | ".join(details)
        )

    source = context.require_output(pipeline.PipelineStage.INPUT)
    geometry = context.require_output(pipeline.PipelineStage.GEOMETRY)
    _require(
        geometry.source_profile_id == args.expected_profile,
        f"Source profile mismatch: {geometry.source_profile_id}",
    )
    _require(
        geometry.source_rig_archetype == args.expected_archetype,
        f"Source archetype mismatch: {geometry.source_rig_archetype}",
    )
    _require(
        geometry.metrics["source_mesh_count"] == len(geometry.blender_objects)
        and source.mesh_count >= 1,
        "Preservation route lost an imported mesh object",
    )
    _require(
        geometry.metrics["vertex_count"] == geometry.metrics["source_vertex_count"]
        and geometry.metrics["polygon_count"]
        == geometry.metrics["source_polygon_count"],
        "Preservation route changed source topology",
    )
    dimensions = _world_dimensions(geometry.blender_objects)
    _require(abs(max(dimensions) - 2.0) < 1.0e-4, f"Normalization failed: {dimensions}")

    completion_report = runner.run(
        pipeline.PipelinePlan(selections=selections[2:]), context
    )
    if not completion_report.success:
        details = [record.result.message for record in completion_report.records]
        details.extend(issue.message for issue in completion_report.issues)
        raise AssertionError(
            "Preserved GLB completion failed: " + " | ".join(details)
        )
    rig = context.require_output(pipeline.PipelineStage.RIG)
    motion = context.require_output(pipeline.PipelineStage.MOTION)
    exported = context.require_output(pipeline.PipelineStage.EXPORT)
    _require(rig.binding_method == "source-preserved", "Source binding was replaced")
    _require(
        rig.armature_object is geometry.armature_object,
        "Source armature identity was not preserved",
    )
    _require(
        motion.root_motion_mode == "PRESERVE",
        "Source root motion was not preserved",
    )
    _require(
        len(motion.clips) == args.expected_animations,
        f"Expected {args.expected_animations} actions, got {len(motion.clips)}",
    )
    _require(
        tuple(clip.action for clip in motion.clips) == geometry.actions,
        "Motion stage replaced source actions",
    )
    spans = {clip.name: _clip_pose_span(rig.armature_object, clip) for clip in motion.clips}
    _require(
        spans and all(span > 1.0e-4 for span in spans.values()),
        f"Preserved source contains a constant clip: {spans}",
    )
    manifest = manifest_module.inspect_glb(exported.path)
    _require(manifest.skin_count >= 1, "Preserved export lost its skin")
    _require(
        len(manifest.animation_names) == args.expected_animations,
        "Preserved export lost source actions",
    )
    score = score_module.score_glb_first_pipeline(context)
    _require(score.score >= 95.0, f"Preserved route score is too low: {score.score}")
    preserved_profile = geometry.source_profile_id
    preserved_archetype = geometry.source_rig_archetype
    preserved_mesh_count = len(geometry.blender_objects)
    preserved_bone_count = len(rig.armature_object.data.bones)
    preserved_action_count = len(motion.clips)

    unsupported = None
    if args.unsupported_input is not None:
        unsupported_path = args.unsupported_input.resolve(strict=True)
        _clear_scene()
        unsupported_context = pipeline.PipelineContext(
            scene=bpy.context.scene,
            metadata={
                "glb_input_path": str(unsupported_path),
                "glb_normalized_extent": 2.0,
            },
        )
        unsupported_report = runner_module.PipelineRunner(registry).run(
            pipeline.PipelinePlan(selections=selections[:2]), unsupported_context
        )
        _require(not unsupported_report.success, "Unsupported rig was preserved")
        _require(
            not bpy.data.objects and not bpy.data.actions,
            "Failed preservation import leaked Blender data: "
            f"objects={tuple(obj.name for obj in bpy.data.objects)}, "
            f"actions={tuple(action.name for action in bpy.data.actions)}",
        )
        unsupported = {
            "path": str(unsupported_path),
            "message": unsupported_report.records[-1].result.message,
        }

    payload = {
        "schema_version": 1,
        "pipeline": "GLB -> preserved Geometry -> source Rig -> source Motion -> GLB",
        "source": {
            "path": str(source_path),
            "profile": preserved_profile,
            "archetype": preserved_archetype,
            "mesh_count": preserved_mesh_count,
            "bone_count": preserved_bone_count,
            "action_count": preserved_action_count,
        },
        "normalization": {
            "dimensions": dimensions,
            "scale": geometry.metrics["normalization_scale"],
        },
        "motion": {"root_mode": motion.root_motion_mode, "pose_spans": spans},
        "export": {
            "path": str(exported.path),
            "sha256": exported.sha256,
            "skin_count": manifest.skin_count,
            "animation_names": manifest.animation_names,
        },
        "score": score.as_dict(),
        "unsupported": unsupported,
    }
    (output_root / "glb_preservation_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "GLB source-preservation smoke: PASS; "
        f"profile={preserved_profile}; archetype={preserved_archetype}; "
        f"meshes={preserved_mesh_count}; actions={preserved_action_count}; "
        f"score={score.score:.2f}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
