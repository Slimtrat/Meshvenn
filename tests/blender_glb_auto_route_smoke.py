"""Run the automatic GLB route through Geometry, Rig, Motion and export."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from pathlib import Path

import bpy


REPO_ROOT = Path(__file__).resolve().parents[1]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--expected-route",
        choices=("canonicalize", "preserve-source", "geometry-only"),
        required=True,
    )
    parser.add_argument("--expected-profile")
    parser.add_argument("--expected-animations", type=int, required=True)
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
    export_path = output_root / "auto-routed.glb"
    export_path.unlink(missing_ok=True)

    package_name = _import_package(args.package_root)
    pipeline = importlib.import_module(f"{package_name}.core.pipeline_contracts")
    runner_module = importlib.import_module(f"{package_name}.core.pipeline_runner")
    registry_module = importlib.import_module(f"{package_name}.core.pipeline_registry")
    score_module = importlib.import_module(f"{package_name}.core.glb_pipeline_score")
    glb_input = importlib.import_module(f"{package_name}.implementations.glb_input")
    auto_route = importlib.import_module(
        f"{package_name}.implementations.glb_auto_route"
    )
    glb_export = importlib.import_module(f"{package_name}.implementations.glb_export")
    manifest_module = importlib.import_module(
        f"{package_name}.implementations.glb_export.manifest"
    )

    _clear_scene()
    bpy.context.scene.frame_set(37)
    implementations = (
        glb_input.GLBFileInputImplementation(),
        auto_route.GLBAutoGeometryImplementation(),
        auto_route.GLBAutoRigImplementation(),
        auto_route.GLBAutoMotionImplementation(),
        glb_export.GLBExportImplementation(),
    )
    registry = registry_module.PipelineRegistry()
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
            "source": "glb-auto-route-smoke",
            "glb_input_path": str(source_path),
            "glb_normalized_extent": 2.0,
            "motion_source_path": "",
            "export_output_path": str(export_path),
            "export_overwrite_existing": False,
            "export_validate_roundtrip": True,
        },
    )
    report = runner_module.PipelineRunner(registry).run(
        pipeline.PipelinePlan(selections=selections), context
    )
    if not report.success:
        details = [record.result.message for record in report.records]
        details.extend(issue.message for issue in report.issues)
        raise AssertionError("Automatic GLB pipeline failed: " + " | ".join(details))
    _require(bpy.context.scene.frame_current == 37, "Pipeline changed the user's timeline frame.")

    _require(
        context.metadata.get("glb_character_route") == args.expected_route,
        f"Incorrect route decision: {context.metadata.get('glb_route_decision')}",
    )
    _require(
        bool(context.metadata.get("glb_route_reason")),
        "Automatic route did not publish an explanation.",
    )
    if args.expected_profile:
        _require(
            context.metadata.get("glb_source_rig_profile") == args.expected_profile,
            f"Incorrect source profile: {context.metadata.get('glb_source_rig_profile')}",
        )
    records = {record.selection.stage: record for record in report.records}
    _require(
        records[pipeline.PipelineStage.GEOMETRY].result.implementation_id
        == "glb-auto-geometry-v1",
        "Automatic Geometry facade did not own its stage result.",
    )
    exported = context.require_output(pipeline.PipelineStage.EXPORT)
    manifest = manifest_module.inspect_glb(exported.path)
    roundtrip = context.metadata.get("glb_export_roundtrip")
    _require(roundtrip and roundtrip["passed"], "Missing export-reimport fidelity evidence.")
    if args.expected_route == "geometry-only" and context.require_output(pipeline.PipelineStage.INPUT).skinned:
        _require(context.metadata.get("glb_route_degraded"), "Rig loss was not reported as degraded.")

    pose_spans = {}
    score = score_module.score_glb_first_pipeline(context)
    _require(score.export_fidelity_score == 100.0, "Export fidelity was not verified.")
    if args.expected_route == "geometry-only":
        _require(
            records[pipeline.PipelineStage.RIG].result.skipped,
            "Geometry-only route did not skip Rig.",
        )
        _require(
            records[pipeline.PipelineStage.MOTION].result.skipped,
            "Geometry-only route did not propagate the Rig skip to Motion.",
        )
        _require(
            not context.has_output(pipeline.PipelineStage.RIG)
            and not context.has_output(pipeline.PipelineStage.MOTION),
            "Geometry-only route published fake Rig or Motion outputs.",
        )
        _require(
            manifest.skin_count == 0 and not manifest.animation_names,
            "Geometry-only export contains unexpected skin or Motion data.",
        )
    else:
        rig = context.require_output(pipeline.PipelineStage.RIG)
        motion = context.require_output(pipeline.PipelineStage.MOTION)
        pose_spans = {
            clip.name: _clip_pose_span(rig.armature_object, clip)
            for clip in motion.clips
        }
        _require(
            pose_spans and all(span > 1.0e-4 for span in pose_spans.values()),
            f"Automatic route produced a constant clip: {pose_spans}",
        )
        _require(manifest.skin_count >= 1, "Automatic route export lost its skin.")
        score = score_module.score_glb_first_pipeline(context)
        _require(score.score >= 95.0, f"Automatic route score is too low: {score.score}")

    _require(
        len(manifest.animation_names) == args.expected_animations,
        "Automatic route export animation count mismatch: "
        f"expected {args.expected_animations}, got {len(manifest.animation_names)}",
    )
    payload = {
        "schema_version": 1,
        "source": str(source_path),
        "route": context.metadata["glb_route_decision"],
        "records": [
            {
                "stage": record.selection.stage.value,
                "state": record.result.state.value,
                "message": record.result.message,
            }
            for record in report.records
        ],
        "motion_pose_spans": pose_spans,
        "export": {
            "path": str(exported.path),
            "sha256": exported.sha256,
            "skin_count": manifest.skin_count,
            "animation_names": manifest.animation_names,
        },
        "score": score.as_dict() if score is not None else None,
        "roundtrip": roundtrip,
    }
    (output_root / "glb_auto_route_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "GLB automatic route smoke: PASS; "
        f"route={args.expected_route}; profile={args.expected_profile or 'none'}; "
        f"skins={manifest.skin_count}; actions={len(manifest.animation_names)}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
