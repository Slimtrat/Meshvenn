"""Run the complete GLB-first INPUT -> GEOMETRY -> RIG -> MOTION -> EXPORT path."""

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
    parser.add_argument("--expected-profile", default="rigged-figure-v1")
    parser.add_argument("--expected-animations", type=int, default=1)
    parser.add_argument("--static-input", type=Path)
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
    """Measure baked pose change through Blender's evaluated animation API."""
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
            if bone.name != "root"
        }
        largest = 0.0
        for frame in frames[1:]:
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            for bone in armature.pose.bones:
                if bone.name == "root":
                    continue
                current = tuple(float(value) for row in bone.matrix for value in row)
                largest = max(
                    largest,
                    max(abs(left - right) for left, right in zip(baseline[bone.name], current)),
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
    export_path = output_root / "glb-first-character.glb"
    export_path.unlink(missing_ok=True)

    package_name = _import_package(args.package_root)
    pipeline = importlib.import_module(f"{package_name}.core.pipeline_contracts")
    runner_module = importlib.import_module(f"{package_name}.core.pipeline_runner")
    registry_module = importlib.import_module(f"{package_name}.core.pipeline_registry")
    score_module = importlib.import_module(f"{package_name}.core.glb_pipeline_score")
    glb_input = importlib.import_module(f"{package_name}.implementations.glb_input")
    glb_geometry = importlib.import_module(f"{package_name}.implementations.glb_geometry")
    canonical_rig = importlib.import_module(f"{package_name}.implementations.canonical_rig")
    canonical_motion = importlib.import_module(
        f"{package_name}.implementations.canonical_motion"
    )
    glb_export = importlib.import_module(f"{package_name}.implementations.glb_export")
    export_manifest = importlib.import_module(
        f"{package_name}.implementations.glb_export.manifest"
    )

    _clear_scene()
    registry = registry_module.PipelineRegistry()
    implementations = (
        glb_input.GLBFileInputImplementation(),
        glb_geometry.GLBNormalizedGeometryImplementation(),
        canonical_rig.CanonicalRigImplementation(),
        canonical_motion.CanonicalMotionRetargetImplementation(),
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
            "source": "glb-first-smoke",
            "glb_input_path": str(source_path),
            "glb_normalized_extent": 2.0,
            "motion_source_path": "",
            "export_output_path": str(export_path),
            "export_overwrite_existing": False,
        },
    )
    runner = runner_module.PipelineRunner(registry)
    preparation_plan = pipeline.PipelinePlan(selections=selections[:2])
    preparation_report = runner.run(preparation_plan, context)
    if not preparation_report.success:
        details = [record.result.message for record in preparation_report.records]
        details.extend(issue.message for issue in preparation_report.issues)
        raise AssertionError("GLB-first preparation failed: " + " | ".join(details))

    geometry = context.require_output(pipeline.PipelineStage.GEOMETRY)
    mesh = geometry.blender_object
    _require(mesh.parent is None, "Normalized GLB geometry kept its source parent")
    _require(not mesh.vertex_groups, "Normalized GLB geometry kept source skin groups")
    _require(
        not any(modifier.type == "ARMATURE" for modifier in mesh.modifiers),
        "Normalized GLB geometry kept a source armature modifier",
    )
    _require(
        context.metadata.get("glb_source_motion_compatible") is True,
        "Source GLB was not classified as Motion-compatible",
    )
    _require(
        context.metadata.get("glb_source_rig_profile") == args.expected_profile,
        "Source GLB profile mismatch: "
        f"{context.metadata.get('glb_source_rig_profile')!r}",
    )
    _require(
        context.metadata.get("glb_source_profile_certification") == "e2e",
        "Smoke fixture is not attached to an E2E-certified source profile",
    )
    _require(
        context.metadata.get("motion_source_path") == str(source_path),
        "GLB input was not reused automatically as Motion source",
    )

    completion_plan = pipeline.PipelinePlan(selections=selections[2:])
    completion_report = runner.run(completion_plan, context)
    if not completion_report.success:
        details = [record.result.message for record in completion_report.records]
        details.extend(issue.message for issue in completion_report.issues)
        raise AssertionError("GLB-first completion failed: " + " | ".join(details))

    exported = context.require_output(pipeline.PipelineStage.EXPORT)
    motion = context.require_output(pipeline.PipelineStage.MOTION)
    clip_pose_spans = {
        clip.name: _clip_pose_span(motion.armature_object, clip) for clip in motion.clips
    }
    _require(
        clip_pose_spans and all(span > 1e-4 for span in clip_pose_spans.values()),
        f"Retargeted profile produced a constant clip: {clip_pose_spans}",
    )
    manifest = export_manifest.inspect_glb(exported.path)
    _require(manifest.skin_count >= 1, "GLB-first export lost its skin")
    _require(
        len(manifest.animation_names) == args.expected_animations,
        "GLB-first export animation count mismatch: "
        f"expected {args.expected_animations}, got {len(manifest.animation_names)}",
    )

    score_without_images = score_module.score_glb_first_pipeline(context)
    score_with_blank_image = score_module.score_glb_first_pipeline(
        context, image_score=0.0
    )
    _require(
        score_without_images.score >= 95.0,
        f"GLB-first score without images is too low: {score_without_images.score:.2f}",
    )
    _require(
        0.0 < score_with_blank_image.score < score_without_images.score,
        "Blank-image evidence did not penalize while preserving the GLB-first score",
    )
    character_geometry_evidence = {
        "object": mesh.name,
        "metrics": dict(geometry.metrics),
        "metadata": dict(geometry.metadata),
    }

    static_evidence = None
    if args.static_input is not None:
        static_source = args.static_input.resolve(strict=True)
        static_export_path = output_root / "glb-first-static.glb"
        static_export_path.unlink(missing_ok=True)
        _clear_scene()
        static_context = pipeline.PipelineContext(
            scene=bpy.context.scene,
            metadata={
                "source": "glb-first-static-smoke",
                "glb_input_path": str(static_source),
                "glb_normalized_extent": 2.0,
                "motion_source_path": "",
                "export_output_path": str(static_export_path),
                "export_overwrite_existing": False,
            },
        )
        static_plan = pipeline.PipelinePlan(
            selections=(selections[0], selections[1], selections[4])
        )
        static_report = runner.run(static_plan, static_context)
        if not static_report.success:
            details = [record.result.message for record in static_report.records]
            details.extend(issue.message for issue in static_report.issues)
            raise AssertionError("Static GLB-first pipeline failed: " + " | ".join(details))
        static_geometry = static_context.require_output(pipeline.PipelineStage.GEOMETRY)
        static_export = static_context.require_output(pipeline.PipelineStage.EXPORT)
        static_manifest = export_manifest.inspect_glb(static_export.path)
        _require(
            static_geometry.metrics["source_mesh_count"] >= 2,
            "Static stress fixture did not exercise multi-mesh normalization",
        )
        _require(
            static_manifest.skin_count == 0 and not static_manifest.animation_names,
            "Static GLB-first export unexpectedly contains Rig or Motion data",
        )
        _require(
            static_manifest.material_count > 0,
            "Static GLB-first normalization lost all source materials",
        )
        _require(
            not bpy.data.cameras and not bpy.data.lights,
            "Static GLB-first normalization leaked source camera/light datablocks",
        )
        static_evidence = {
            "source_path": str(static_source),
            "source_mesh_count": static_geometry.metrics["source_mesh_count"],
            "normalized_vertex_count": static_geometry.metrics["vertex_count"],
            "normalized_polygon_count": static_geometry.metrics["polygon_count"],
            "export_path": str(static_export.path),
            "export_sha256": static_export.sha256,
            "material_count": static_manifest.material_count,
        }

    unsupported_evidence = None
    if args.unsupported_input is not None:
        unsupported_source = args.unsupported_input.resolve(strict=True)
        _clear_scene()
        unsupported_context = pipeline.PipelineContext(
            scene=bpy.context.scene,
            metadata={
                "source": "glb-first-unsupported-smoke",
                "glb_input_path": str(unsupported_source),
                "glb_normalized_extent": 2.0,
                "motion_source_path": "",
            },
        )
        unsupported_report = runner.run(preparation_plan, unsupported_context)
        if not unsupported_report.success:
            details = [record.result.message for record in unsupported_report.records]
            details.extend(issue.message for issue in unsupported_report.issues)
            raise AssertionError(
                "Unsupported-rig GLB preparation failed unexpectedly: "
                + " | ".join(details)
            )
        _require(
            unsupported_context.metadata["glb_source_motion_compatible"] is False,
            "Unsupported source rig was classified as Motion-compatible",
        )
        _require(
            unsupported_context.metadata["motion_source_path"] == "",
            "Unsupported source rig was automatically selected for Motion",
        )
        unsupported_geometry = unsupported_context.require_output(
            pipeline.PipelineStage.GEOMETRY
        )
        unsupported_evidence = {
            "source_path": str(unsupported_source),
            "rig_profile": unsupported_context.metadata["glb_source_rig_profile"],
            "motion_compatible": False,
            "vertex_count": unsupported_geometry.metrics["vertex_count"],
        }

    payload = {
        "schema_version": 2,
        "pipeline": "GLB INPUT -> normalized GEOMETRY -> canonical RIG -> MOTION -> GLB EXPORT",
        "source": {
            "path": str(source_path),
            "sha256": context.metadata["glb_input_sha256"],
            "rig_profile": context.metadata["glb_source_rig_profile"],
            "profile_certification": context.metadata[
                "glb_source_profile_certification"
            ],
            "motion_compatible": context.metadata["glb_source_motion_compatible"],
        },
        "geometry": character_geometry_evidence,
        "export": {
            "path": str(exported.path),
            "size_bytes": exported.size_bytes,
            "sha256": exported.sha256,
            "skin_count": manifest.skin_count,
            "animation_names": manifest.animation_names,
        },
        "motion": {
            "source_profile": context.metadata["motion_source_profile"],
            "profile_certification": context.metadata[
                "motion_source_profile_certification"
            ],
            "clip_pose_spans": clip_pose_spans,
        },
        "score_without_images": score_without_images.as_dict(),
        "score_with_blank_image": score_with_blank_image.as_dict(),
        "static_multi_mesh": static_evidence,
        "unsupported_rig": unsupported_evidence,
    }
    (output_root / "glb_first_report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "GLB-first pipeline smoke: PASS; "
        f"profile={context.metadata['glb_source_rig_profile']}; "
        f"score(no images)={score_without_images.score:.2f}; "
        f"score(blank image)={score_with_blank_image.score:.2f}; "
        f"skin={manifest.skin_count}; animations={len(manifest.animation_names)}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
