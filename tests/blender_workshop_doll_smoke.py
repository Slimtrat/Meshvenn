"""Real doll relocation, No Rebuild, static migration, face editing and rollback."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import bpy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    repository = Path(__file__).resolve().parents[1]
    parser.add_argument("--fixture", type=Path, default=repository / "example/v2/modular/StytchDoll")
    parser.add_argument("--package-root", type=Path, default=repository)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    root, fixture, output = args.package_root.resolve(), args.fixture.resolve(), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty smoke-test directory.")
    output.mkdir(parents=True, exist_ok=True)
    relocated = output / "relocated"
    relocated.mkdir()
    for name in ("source.blend", "authoring.json"):
        shutil.copy2(fixture / name, relocated / name)
    sys.path.insert(0, str(repository))
    sys.path.insert(0, str(root.parent))
    package = importlib.import_module(root.name)
    package.register()

    def module(name):
        return importlib.import_module(f"{root.name}.{name}")

    def rejected(call):
        try:
            call()
        except (ValueError, TypeError, FileNotFoundError, FileExistsError):
            return
        raise AssertionError("Invalid declaration was accepted.")

    try:
        bpy.ops.wm.open_mainfile(filepath=str(relocated / "source.blend"), use_scripts=False)
        api = module("implementations.glb_export.modular_source")
        editor = module("implementations.glb_export.face_authoring")
        pipeline = module("core.pipeline_contracts")
        reader = module("implementations.glb_export.modular_gltf")
        settings = bpy.context.scene.bpt_settings
        assert settings.export_modular_manifest_path == "//authoring.json"
        assert settings.export_output_path == "//character.glb"
        context = api.context_from_authored_scene(bpy.context.scene, output_path="//reexport.glb")
        mesh = context.require_output(pipeline.PipelineStage.GEOMETRY).blender_object
        rig = context.require_output(pipeline.PipelineStage.RIG).armature_object
        assert len(rig.data.bones) == 18 and not context.has_output(pipeline.PipelineStage.MOTION)
        previews = [obj for obj in bpy.context.scene.objects if obj.get("meshvenn_source_mesh") == mesh.name]
        assert len(previews) == 5 and all(not obj.hide_render and not obj.hide_get() for obj in previews)
        assert len([obj for obj in bpy.context.scene.objects if obj.type == "MESH"]) == 6
        assert not context.has_output(pipeline.PipelineStage.INPUT)
        from scripts.author_stytch_doll import source_snapshot
        before = source_snapshot(mesh, rig)
        manifest = json.loads((fixture / "manifest.json").read_text("utf-8"))
        authority_digest = hashlib.sha256(json.dumps(before, sort_keys=True, allow_nan=False).encode()).hexdigest()
        assert authority_digest == manifest["source_authority_sha256"], "Relocation changed the pinned source authority."
        assert all(image.packed_file is not None and image.filepath.replace("\\", "/").startswith("//packed/") for image in bpy.data.images)
        assert {p.name for p in relocated.iterdir()} == {"source.blend", "authoring.json"}
        settings.export_output_path = "//reexport.glb"
        bpy.context.scene.frame_set(17, subframe=.375)
        # A selected original armature must never join the importer's multi-edit
        # session. Its parent-composed rest matrices must remain bit-exact.
        rig.hide_set(False)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        selected_before = tuple(bpy.context.selected_objects)
        forbidden = (("implementations.projection_images", "ProjectionImagesImplementation"),
                     ("implementations.native_visual_hull", "NativeVisualHullImplementation"),
                     ("implementations.uv_bake", "UVBakeImplementation"),
                     ("implementations.canonical_rig_v2", "CanonicalRigV2Implementation"),
                     ("implementations.canonical_motion", "CanonicalMotionRetargetImplementation"))
        with ExitStack() as guards:
            for module_name, class_name in forbidden:
                cls = getattr(module(module_name), class_name)
                guards.enter_context(patch.object(cls, "execute", side_effect=AssertionError("Rebuild is forbidden.")))
            assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
        from scripts.author_stytch_doll import assert_source_unchanged
        assert_source_unchanged(before, source_snapshot(mesh, rig), output)
        assert tuple(bpy.context.selected_objects) == selected_before
        assert bpy.context.view_layer.objects.active is rig and rig.mode == "OBJECT"
        assert (bpy.context.scene.frame_current, bpy.context.scene.frame_subframe) == (17, .375)
        published = (relocated / "reexport.glb").read_bytes()
        result = module("operators.runtime").get_last_pipeline_context(bpy.context.scene).require_output(pipeline.PipelineStage.EXPORT)
        assert result.metadata["roundtrip"]["modular_character"]["passed"]
        document, binary = reader.read_glb(relocated / "reexport.glb")
        reference, reference_binary = reader.read_glb(fixture / "reference.glb")
        from scripts.workshop_doll_evidence import compare_reference
        evidence = compare_reference(reference, reference_binary, document, binary, reader.read_accessor)
        assert evidence["passed"] and evidence["max_weight_error"] == 0 and evidence["max_inverse_bind_error"] == 0
        from scripts.render_v2_pipeline_preview import _joint_world
        from mathutils import Matrix, Quaternion, Vector
        world = _joint_world(document)
        envelope = document["asset"]["extras"]["meshvenn_modular_character"]
        expected_matrices = {item["socket_id"]: Matrix(item["authored_gltf_world_matrix"]) for item in manifest["socket_authoring"]}
        socket_error = 0.0
        for socket in envelope["spec"]["sockets"]:
            rotation = socket["rotation"]
            local = Matrix.LocRotScale(Vector(socket["translation"]), Quaternion((rotation[3], *rotation[:3])), Vector(socket["scale"]))
            actual = world(envelope["bindings"]["joint_nodes"][socket["parent_bone"]]) @ local
            socket_error = max(socket_error, max(abs(a-b) for row_a, row_b in zip(actual, expected_matrices[socket["id"]]) for a,b in zip(row_a,row_b)))
        assert socket_error <= 2e-5

        # Editing operations preserve corner/skin/material authority in both modes.
        mesh.hide_set(False)
        mesh.hide_render = False
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        spec = editor._read(relocated / "authoring.json")
        values = [item.value for item in mesh.data.attributes[editor.ATTRIBUTE].data]
        saved_state = mesh[editor.STATE_KEY]
        for invalid_state in ("[]", '{"schema_version":true}', '{"schema_version":1,"schema_version":1}'):
            mesh[editor.STATE_KEY] = invalid_state
            rejected(lambda: editor.assign_selected_faces(mesh, "body-core"))
        del mesh[editor.STATE_KEY]
        rejected(lambda: editor.load_face_ownership(mesh, spec, replace_existing=True))
        mesh[editor.STATE_KEY] = saved_state
        rejected(lambda: editor.load_face_ownership(mesh, spec))
        rejected(lambda: editor.assign_selected_faces(mesh, "undeclared"))
        assert values == [item.value for item in mesh.data.attributes[editor.ATTRIBUTE].data]
        for face in mesh.data.polygons:
            face.select = False
        rejected(lambda: editor.assign_selected_faces(mesh, "body-core"))
        vertex = mesh.data.vertices[0]
        position = vertex.co.copy()
        try:
            vertex.co.x += .001
            rejected(lambda: editor.assign_selected_faces(mesh, "body-core"))
            rejected(lambda: api.context_from_authored_scene(bpy.context.scene, output_path="//bad.glb"))
        finally:
            vertex.co = position
        body_face = next(index for index, owner in enumerate(spec.ownership[mesh.name]) if owner == "body-core")
        mesh.data.polygons[body_face].select = True
        assert editor.assign_selected_faces(mesh, "left-arm") == 1
        saved_json = (relocated / "authoring.json").read_bytes()
        rejected(lambda: editor.save_face_ownership(mesh, relocated / "authoring.json", relocated / "bad.blend"))
        rejected(lambda: editor.save_face_ownership(mesh, relocated / "authoring.json", relocated / "missing" / "bad.json"))
        rejected(lambda: editor.save_face_ownership(mesh, relocated / "authoring.json", relocated / "authoring.json"))
        editor.save_face_ownership(mesh, relocated / "authoring.json", relocated / "edited.json")
        assert editor._read(relocated / "edited.json").ownership[mesh.name][body_face] == "left-arm"
        assert (relocated / "authoring.json").read_bytes() == saved_json
        editor.load_face_ownership(mesh, spec, replace_existing=True)
        import bmesh
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(mesh.data)
        for face in bm.faces:
            face.select_set(False)
        bm.faces.ensure_lookup_table()
        bm.faces[body_face].select_set(True)
        assert bpy.ops.bpt.assign_modular_faces(region_id="left-arm") == {"FINISHED"}
        assert editor.spec_from_face_ownership(mesh, spec).ownership[mesh.name][body_face] == "left-arm"
        bpy.ops.object.mode_set(mode="OBJECT")
        editor.load_face_ownership(mesh, spec, replace_existing=True)
        for face in mesh.data.polygons:
            face.select = True
        editor.assign_selected_faces(mesh, "body-core")
        rejected(lambda: editor.save_face_ownership(mesh, relocated / "authoring.json", relocated / "invalid.json"))
        assert not (relocated / "invalid.json").exists()
        editor.load_face_ownership(mesh, spec, replace_existing=True)
        mesh.data.attributes[editor.ATTRIBUTE].data[0].value = 0
        rejected(lambda: editor.spec_from_face_ownership(mesh, spec))
        editor.load_face_ownership(mesh, spec, replace_existing=True)
        assert source_snapshot(mesh, rig) == before

        # Explicit old-static migration is not a fallback from a broken catalogue.
        rejected(lambda: api.context_from_authored_scene(bpy.context.scene, output_path="//bad.glb", initialize_static_source=True, binding_method="canonical-envelope-v2"))
        previous_reference = mesh[api.CATALOGUE_REFERENCE]
        del mesh[api.CATALOGUE_REFERENCE]
        rejected(lambda: api.context_from_authored_scene(bpy.context.scene, output_path="//bad.glb"))
        initialize = lambda: api.context_from_authored_scene(bpy.context.scene, output_path="//initialized.glb", initialize_static_source=True, binding_method="canonical-envelope-v2")
        prepared = initialize()
        assert not prepared.has_output(pipeline.PipelineStage.MOTION)
        prepared.prepared_modular_source.discard()
        rejected(lambda: api.context_from_authored_scene(bpy.context.scene, output_path="//bad.glb", initialize_static_source=True, binding_method="guess"))
        rig.animation_data_create()
        action = bpy.data.actions.new("DoNotDropThisAction")
        rig.animation_data.action = action
        rejected(initialize)
        rig.keyframe_insert(data_path="location", frame=1)
        rig.animation_data.action = None
        rig.driver_add("location", 0)
        rejected(initialize)
        rig.driver_remove("location", 0)
        for animated in (mesh, mesh.data, rig.data, mesh.parent, rig.parent):
            if animated is None:
                continue
            own_action = bpy.data.actions.new("DoNotDropSourceHierarchyAction")
            animated.animation_data_create()
            animated.animation_data.action = own_action
            rejected(initialize)
            animated.animation_data.action = None
            bpy.data.actions.remove(own_action)
        track = rig.animation_data.nla_tracks.new()
        track.strips.new("MustNotDropNLA", 1, action)
        rejected(initialize)
        rig.animation_data.nla_tracks.remove(track)
        bpy.data.actions.remove(action)
        texts = set(bpy.data.texts)
        failed = pipeline.StageExecutionResult.failed_result(stage=pipeline.PipelineStage.EXPORT, implementation_id="glb-export-v1", message="Injected static initialization failure")
        exporter = module("implementations.glb_export")
        settings.export_output_path = "//initialized.glb"
        with patch.object(exporter.GLBExportImplementation, "execute", return_value=failed):
            try:
                status = bpy.ops.bpt.export_existing_modular_source(initialize_static_source=True, binding_method="canonical-envelope-v2")
                assert status == {"CANCELLED"}
            except RuntimeError as exc:
                assert failed.message in str(exc)
        assert api.CATALOGUE_REFERENCE not in mesh and set(bpy.data.texts) == texts
        assert not (relocated / "initialized.glb").exists()
        with ExitStack() as guards:
            for module_name, class_name in forbidden:
                guards.enter_context(patch.object(getattr(module(module_name), class_name), "execute", side_effect=AssertionError("Rebuild is forbidden.")))
            assert bpy.ops.bpt.export_existing_modular_source(initialize_static_source=True, binding_method="canonical-envelope-v2") == {"FINISHED"}
        assert mesh[api.CATALOGUE_REFERENCE] != previous_reference
        assert bpy.data.texts[mesh[api.CATALOGUE_REFERENCE]]["meshvenn_catalogue_committed"]
        assert not api.context_from_authored_scene(bpy.context.scene, output_path="//next.glb").has_output(pipeline.PipelineStage.MOTION)
        assert (relocated / "reexport.glb").read_bytes() == published
        assert source_snapshot(mesh, rig) == before
        (output / "report.json").write_text(json.dumps({"passed": True, "relocated_without_inputs": True,
            "static_initialization_rollback": True, "edit_mode_face_assignment": True,
            "native_joints": 18, "triangle_count": 14252, "socket_world_trs_max_error": socket_error,
            "reference_fidelity": evidence, "roundtrip": result.metadata["roundtrip"]["modular_character"]}, indent=2), "utf-8")
        print("Workshop doll relocation/editor/static initialization PASS; five regions, eight sockets, 18 joints, 14252 triangles.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
