"""Real-source authored skin edit, exact rollback, rejection and relocated export."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import bpy


def main():
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=repository)
    parser.add_argument("--variant", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    output, root = args.output.resolve(), args.package_root.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty test output directory.")
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(repository))
    sys.path.insert(0, str(root.parent))
    package = importlib.import_module(root.name)
    package.register()

    def module(name):
        return importlib.import_module(f"{root.name}.{name}")

    try:
        api = module("implementations.canonical_rig_v2.owned_refinement")
        loader = module("implementations.glb_export.modular_source")
        bpy.ops.wm.open_mainfile(filepath=str(repository / "example/v2/modular/StytchDoll/source.blend"), use_scripts=False)
        mesh, rig = bpy.data.objects["MeshvennScan"], bpy.data.objects["MeshvennCanonicalRig"]
        spec = module("implementations.glb_export.face_authoring")._read(repository / "example/v2/modular/StytchDoll/authoring.json")
        from scripts.author_stytch_doll import source_snapshot
        before = source_snapshot(mesh, rig)
        properties = dict(mesh.items())

        def rejected(call):
            try:
                call()
            except (TypeError, ValueError):
                return
            raise AssertionError("Unsafe skin refinement accepted.")

        mesh["meshvenn_source_mesh"] = mesh.name
        rejected(lambda: api.refine_owned_skin(mesh, spec))
        del mesh["meshvenn_source_mesh"]
        other = bpy.data.objects.new("SharedSkinTest", mesh.data)
        try:
            rejected(lambda: api.refine_owned_skin(mesh, spec))
        finally:
            bpy.data.objects.remove(other)
        unknown = mesh.vertex_groups.new(name="DoNotSilentlyIgnore")
        unknown.add((0,), 1., "REPLACE")
        rejected(lambda: api.refine_owned_skin(mesh, spec))
        mesh.vertex_groups.remove(unknown)
        assert source_snapshot(mesh, rig) == before
        with patch.object(api.json, "dumps", side_effect=RuntimeError("Injected post-weight failure")):
            try:
                api.refine_owned_skin(mesh, spec)
            except RuntimeError as exc:
                assert "Injected" in str(exc)
            else:
                raise AssertionError("Failure injection missed.")
        assert source_snapshot(mesh, rig) == before
        assert dict(mesh.items()) == properties
        mesh.hide_set(False)
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.object.mode_set(mode="EDIT")
        rejected(lambda: api.refine_owned_skin(mesh, spec))
        bpy.ops.object.mode_set(mode="OBJECT")
        assert bpy.ops.bpt.refine_owned_skin() == {"FINISHED"}
        after = source_snapshot(mesh, rig)
        assert {k: v for k, v in before.items() if k != "weights"} == {k: v for k, v in after.items() if k != "weights"}
        edit = json.loads(mesh["meshvenn_owned_skin_refinement"])
        assert edit["changed_vertex_count"] > 0 and edit["unchanged_distal_vertex_count"] > 0
        rejected(lambda: api.refine_owned_skin(mesh, spec))
        rejected(lambda: module("implementations.canonical_rig_v2.head_refinement").refine_head_weights(mesh))
        assert source_snapshot(mesh, rig) == after
        assert not mesh.hide_get() and not mesh.hide_render
        previews = [obj for obj in bpy.context.scene.objects if obj.get("meshvenn_source_mesh") == mesh.name]
        assert len(previews) == 5 and all(obj.hide_get() and obj.hide_render for obj in previews)
        roundtrip = None
        if args.variant:
            variant = args.variant.resolve(strict=True)
            manifest = json.loads((variant / "manifest.json").read_text("utf-8"))
            relocated = output / "relocated"
            relocated.mkdir()
            for name in ("source.blend", "authoring.json"):
                shutil.copy2(variant / name, relocated / name)
            bpy.ops.wm.open_mainfile(filepath=str(relocated / "source.blend"), use_scripts=False)
            mesh, rig = bpy.data.objects["MeshvennScan"], bpy.data.objects["MeshvennCanonicalRig"]
            source = source_snapshot(mesh, rig)
            assert len(rig.data.bones) == 18
            bpy.context.scene.bpt_settings.export_output_path = "//reexport.glb"
            assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
            assert source_snapshot(mesh, rig) == source
            pipeline = module("operators.runtime").get_last_pipeline_context(bpy.context.scene)
            result = pipeline.require_output(module("core.pipeline_contracts").PipelineStage.EXPORT)
            roundtrip = result.metadata["roundtrip"]["modular_character"]
            assert roundtrip["passed"] and not result.animation_names
            reader = module("implementations.glb_export.modular_gltf")
            from scripts.workshop_doll_evidence import compare_reference
            old, old_binary = reader.read_glb(variant / "character.glb")
            new, new_binary = reader.read_glb(result.path)
            proof = compare_reference(old, old_binary, new, new_binary, reader.read_accessor)
            assert proof["max_weight_error"] == proof["max_inverse_bind_error"] == 0
            assert old["asset"]["extras"]["meshvenn_modular_character"]["spec"] == new["asset"]["extras"]["meshvenn_modular_character"]["spec"]
            assert manifest["body_refinement"]["algorithm"] == mesh["meshvenn_rig_skinning_algorithm"]
            # Explicit first export of an edited old static source is supported.
            del mesh[loader.CATALOGUE_REFERENCE]
            initialized = loader.context_from_authored_scene(bpy.context.scene,
                output_path=str(relocated / "initialized.glb"), initialize_static_source=True,
                binding_method="canonical-envelope-v2")
            result = module("implementations.glb_export").GLBExportImplementation().execute(initialized)
            assert result.success, result.message
            assert source_snapshot(mesh, rig) == source
        (output / "report.json").write_text(json.dumps({"passed": True, "exact_post_write_rollback": True,
            "unsafe_edits_rejected": True, "source_surface_materials_rest_joints_preserved": True,
            "distal_weights_preserved": True, "edit": edit, "relocated_roundtrip": roundtrip}, indent=2), "utf-8")
        print("Authored skin PASS: exact rollback, local authority, source surface/atlas/rest rig unchanged.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
