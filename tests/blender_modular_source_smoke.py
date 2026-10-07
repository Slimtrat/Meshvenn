"""Relocate and re-export the actual editable source, with reconstruction forbidden."""

from __future__ import annotations

import argparse
from dataclasses import replace
import importlib
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import warnings
from unittest.mock import patch

import bpy


def _snapshot(sources, armature):
    animation = armature.animation_data
    return {
        "objects": set(bpy.data.objects), "meshes": set(bpy.data.meshes), "actions": set(bpy.data.actions),
        "frame": (bpy.context.scene.frame_current, bpy.context.scene.frame_subframe),
        "selected": tuple(bpy.context.selected_objects), "active": bpy.context.view_layer.objects.active,
        "visibility": {obj.name: (obj.hide_get(), obj.hide_viewport, obj.hide_render, obj.hide_select)
                       for obj in bpy.context.scene.objects},
        "sources": {obj.name: (obj.data, obj.matrix_world.copy(), tuple(tuple(v.co) for v in obj.data.vertices),
                                tuple(tuple(face.vertices) for face in obj.data.polygons),
                                tuple((group.name, group.index) for group in obj.vertex_groups)) for obj in sources},
        "action": animation.action if animation else None,
        "action_slot": getattr(animation, "action_slot", None) if animation else None,
        "use_nla": animation.use_nla if animation else None,
        "pose": {bone.name: (bone.rotation_mode, bone.matrix_basis.copy()) for bone in armature.pose.bones},
    }


def _assert_snapshot(expected, sources, armature):
    actual = _snapshot(sources, armature)
    for key in ("objects", "meshes", "actions", "frame", "selected", "active", "visibility", "sources",
                "action", "action_slot", "use_nla"):
        assert actual[key] == expected[key], f"Existing-source re-export changed {key}."
    for name, (mode, matrix) in expected["pose"].items():
        assert actual["pose"][name][0] == mode
        assert max(abs(a - b) for row_a, row_b in zip(actual["pose"][name][1], matrix)
                   for a, b in zip(row_a, row_b)) < 1e-6, name


def main():
    warnings.filterwarnings("error", message=r".*does not support blend relative.*", category=RuntimeWarning)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    root, source = args.package_root.resolve(), args.input_source.resolve(strict=True)
    assert source.suffix == ".blend" and (source.parent / "authoring.json").is_file()
    relocated = args.output.resolve() / "relocated"
    relocated.mkdir(parents=True, exist_ok=True)
    target_source = relocated / "source.blend"
    assert target_source.resolve() != source
    shutil.copy2(source, target_source)
    shutil.copy2(source.parent / "authoring.json", relocated / "authoring.json")
    sys.path.insert(0, str(root.parent))
    package = importlib.import_module(root.name)
    package.register()
    try:
        result = bpy.ops.wm.open_mainfile(filepath=str(target_source))
        assert "FINISHED" in result
        settings = bpy.context.scene.bpt_settings
        property_module = importlib.import_module(f"{root.name}.properties.settings")
        legacy_rna = SimpleNamespace(types=SimpleNamespace(StringProperty=SimpleNamespace(
            bl_rna=SimpleNamespace(properties={}))))
        with patch.object(property_module, "bpy", legacy_rna):
            assert property_module._blend_relative_path_options() == {"ANIMATABLE"}
        for name in ("export_output_path", "export_modular_manifest_path"):
            prop = settings.bl_rna.properties[name]
            if hasattr(prop, "is_path_supports_blend_relative"):
                assert prop.is_path_supports_blend_relative, name
        assert settings.export_modular_character
        assert settings.export_modular_manifest_path == "//authoring.json"
        assert settings.export_output_path == "//character.glb"
        appearance_text = bpy.data.texts.get("meshvenn-material-input.json")
        if appearance_text is not None:
            appearance = json.loads(appearance_text.as_string())
            assert appearance["atlas_storage"] == "srgb-byte-from-scene-linear"
            assert appearance["color_transport"]["passed"]
            assert len(appearance["views"]) == 10
            for record in appearance["views"]:
                image = bpy.data.images[record["packed_image"]]
                assert image.packed_file is not None and image.use_fake_user
                assert hashlib.sha256(image.packed_file.data).hexdigest() == record["sha256"]
            selections = importlib.import_module(f"{root.name}.properties.pipeline")
            assert settings.pipeline.initialized
            expected = {"input": "projection-images", "geometry": "native-visual-hull",
                        "material": "uv-bake-v2", "rig": "canonical-biped-v2",
                        "motion": "canonical-motion-retarget-v1", "export": "glb-export-v1"}
            for name, identifier in expected.items():
                selected = selections.pipeline_stage_settings(settings, name)
                assert selected.implementation_id == identifier and selected.enabled, (name, selected.implementation_id)
        settings.export_output_path = "//reexport.glb"
        settings.export_overwrite_existing = True
        api = importlib.import_module(f"{root.name}.implementations.glb_export.modular_source")
        pipeline = importlib.import_module(f"{root.name}.core.pipeline_contracts")
        runtime = importlib.import_module(f"{root.name}.operators.runtime")
        gltf = importlib.import_module(f"{root.name}.implementations.glb_export.modular_gltf")
        strict = importlib.import_module(f"{root.name}.core.modular_character.json_io").strict_json_loads
        # The only files in this relocated bundle are .blend and authoring JSON.
        assert {path.name for path in relocated.iterdir()} == {"source.blend", "authoring.json"}
        context = api.context_from_authored_scene(bpy.context.scene)
        geometry = context.require_output(pipeline.PipelineStage.GEOMETRY)
        rig = context.require_output(pipeline.PipelineStage.RIG)
        motion = context.require_output(pipeline.PipelineStage.MOTION)
        assert len(rig.armature_object.data.bones) == 18
        assert len(motion.clips) == 43
        assert not context.has_output(pipeline.PipelineStage.INPUT)
        assert not context.metadata.get("motion_source_path") and not context.metadata.get("glb_input_path")
        bpy.context.scene.frame_set(17, subframe=0.375)
        snapshot = _snapshot(geometry.blender_objects, rig.armature_object)
        planning = importlib.import_module(f"{root.name}.implementations.glb_export.planning")
        plan = planning.build_export_plan(context)
        saved_texts = set(bpy.data.texts)
        saved_references = {obj: obj[api.CATALOGUE_REFERENCE] for obj in geometry.blender_objects}

        def rejected_staging(candidate=plan):
            try:
                staged = api.stage_authored_scene_catalogue(candidate)
            except (ValueError, TypeError):
                pass
            else:
                api.discard_uncommitted_catalogue(staged)
                raise AssertionError("Inconsistent source provenance passed publication preflight.")
            assert set(bpy.data.texts) == saved_texts
            assert {obj: obj[api.CATALOGUE_REFERENCE] for obj in geometry.blender_objects} == saved_references
            assert not (relocated / "reexport.glb").exists()

        source_object = geometry.blender_object
        for key, replacement in (("bpt_normalize_height", False), ("bpt_target_height", 9.0),
                                 ("meshvenn_normalization_scale", float("nan")),
                                 ("meshvenn_rig_semantics", "{}")):
            previous = source_object[key]
            try:
                source_object[key] = replacement
                rejected_staging()
            finally:
                source_object[key] = previous
        previous = rig.armature_object["meshvenn_rig_implementation"]
        try:
            rig.armature_object["meshvenn_rig_implementation"] = "canonical-biped-v1"
            rejected_staging()
        finally:
            rig.armature_object["meshvenn_rig_implementation"] = previous
        binding = next(modifier for modifier in source_object.modifiers if modifier.type == "ARMATURE")
        try:
            binding.object = None
            rejected_staging()
        finally:
            binding.object = rig.armature_object
        first = motion.clips[0]
        invalid_motion = replace(motion, clips=(replace(first, frame_end=first.frame_end + 1), *motion.clips[1:]))
        rejected_staging(replace(plan, motion=invalid_motion))
        previous_fps = bpy.context.scene.render.fps
        try:
            bpy.context.scene.render.fps += 1
            rejected_staging()
        finally:
            bpy.context.scene.render.fps = previous_fps
        staged = api.stage_authored_scene_catalogue(plan)
        assert staged.use_fake_user
        api.discard_uncommitted_catalogue(staged)
        assert set(bpy.data.texts) == saved_texts
        _assert_snapshot(snapshot, geometry.blender_objects, rig.armature_object)
        upstream = (
            ("implementations.projection_images", "ProjectionImagesImplementation"),
            ("implementations.native_visual_hull", "NativeVisualHullImplementation"),
            ("implementations.canonical_rig_v2", "CanonicalRigV2Implementation"),
            ("implementations.canonical_motion", "CanonicalMotionRetargetImplementation"),
        )
        from contextlib import ExitStack
        with ExitStack() as forbidden:
            for module_name, class_name in upstream:
                implementation = getattr(importlib.import_module(f"{root.name}.{module_name}"), class_name)
                forbidden.enter_context(patch.object(implementation, "execute", side_effect=AssertionError(
                    "Re-export must not reconstruct, re-fit or retarget the authoritative source.")))
            result = bpy.ops.bpt.export_existing_modular_source()
            assert "FINISHED" in result
        _assert_snapshot(snapshot, geometry.blender_objects, rig.armature_object)
        exported_context = runtime.get_last_pipeline_context(bpy.context.scene)
        exported = exported_context.require_output(pipeline.PipelineStage.EXPORT)
        output = relocated / "reexport.glb"
        assert exported.path == output
        assert exported.metadata["roundtrip"]["modular_character"]["passed"]
        document, _ = gltf.read_glb(output)
        assert len(document["skins"]) == 1 and len(document["skins"][0]["joints"]) == 18
        assert len(document["animations"]) == 43
        assert {item["name"] for item in document["animations"]} == {clip.action.name for clip in motion.clips}
        assert all("uri" not in image for image in document.get("images", []))
        assert document["asset"]["extras"]["meshvenn_modular_character"]["spec"] == strict(
            (relocated / "authoring.json").read_text("utf-8"))
        published = output.read_bytes()

        def rejected():
            try:
                api.context_from_authored_scene(bpy.context.scene)
            except (ValueError, FileNotFoundError, TypeError):
                pass
            else:
                raise AssertionError("Invalid authored source was accepted without re-authoring.")
            assert output.read_bytes() == published

        settings.export_modular_character = False
        rejected()
        settings.export_modular_character = True
        settings.export_modular_manifest_path = "//missing-authoring.json"
        rejected()
        settings.export_modular_manifest_path = "//authoring.json"
        action = motion.clips[0].action
        previous_name = action.name
        action.name = "TemporarilyMissingNativeAction"
        rejected()
        action.name = previous_name
        vertex = geometry.blender_object.data.vertices[0]
        previous_position = vertex.co.copy()
        vertex.co.x += 0.001
        try:
            rejected()
        finally:
            vertex.co = previous_position
        references = [(obj, obj[api.CATALOGUE_REFERENCE]) for obj in geometry.blender_objects]
        for obj, _ in references:
            del obj[api.CATALOGUE_REFERENCE]
        rejected()
        for obj, name in references:
            obj[api.CATALOGUE_REFERENCE] = name
        authority = relocated / "authority.glb"
        authority.write_bytes((relocated / "authoring.json").read_bytes())
        settings.export_modular_manifest_path = "//authority.glb"
        settings.export_output_path = "//authority.glb"
        rejected()
        assert authority.read_bytes() == (relocated / "authoring.json").read_bytes()
        settings.export_modular_manifest_path = "//authoring.json"
        settings.export_output_path = "//reexport.glb"
        _assert_snapshot(snapshot, geometry.blender_objects, rig.armature_object)

        # Store/display a failed direct export too: both runtime message helpers
        # must work without the normal reconstruction runner's call path.
        implementation_module = importlib.import_module(f"{root.name}.implementations.glb_export")
        failed = pipeline.StageExecutionResult.failed_result(
            stage=pipeline.PipelineStage.EXPORT, implementation_id="glb-export-v1",
            message="Injected existing-source export failure")
        failure_texts = set(bpy.data.texts)
        failure_references = {obj: obj[api.CATALOGUE_REFERENCE] for obj in geometry.blender_objects}
        with patch.object(implementation_module.GLBExportImplementation, "execute", return_value=failed):
            try:
                result = bpy.ops.bpt.export_existing_modular_source()
            except RuntimeError as exc:
                assert failed.message in str(exc)
            else:
                assert "CANCELLED" in result
        failure_report = runtime.get_last_pipeline_report(bpy.context.scene)
        assert failure_report.failed and failure_report.result_for(pipeline.PipelineStage.EXPORT) is failed
        assert bpy.context.scene["meshvenn_last_pipeline_status"] == "failed"
        assert failed.message in bpy.context.scene["meshvenn_last_pipeline_message"]
        assert output.read_bytes() == published
        assert set(bpy.data.texts) == failure_texts
        assert {obj: obj[api.CATALOGUE_REFERENCE] for obj in geometry.blender_objects} == failure_references
        _assert_snapshot(snapshot, geometry.blender_objects, rig.armature_object)

        # A real static product export persists explicit no-motion provenance.
        static_context = api.context_from_authored_scene(bpy.context.scene, output_path="//static.glb", overwrite_existing=True)
        static_context.outputs.pop(pipeline.PipelineStage.MOTION)
        authored = importlib.import_module(f"{root.name}.implementations.authored_source")
        stale = implementation_module.GLBExportImplementation().execute(static_context)
        assert stale.failed and "stale" in stale.message
        authored.prepare_authored_source(static_context, replace_existing=True)
        implementation = implementation_module.GLBExportImplementation()
        static_result = implementation.execute(static_context)
        assert static_result.success, static_result.message
        static_reopened = api.context_from_authored_scene(bpy.context.scene, output_path="//static-reexport.glb", overwrite_existing=True)
        assert not static_reopened.has_output(pipeline.PipelineStage.MOTION)
        static_document, _ = gltf.read_glb(static_result.payload.path)
        assert not static_document.get("animations")
        assert len(static_document["skins"][0]["joints"]) == 18
        _assert_snapshot(snapshot, geometry.blender_objects, rig.armature_object)
        print("Existing modular source relocation/re-export smoke: PASS; 18 joints, 43 clips, static declarations, no reconstruction")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
