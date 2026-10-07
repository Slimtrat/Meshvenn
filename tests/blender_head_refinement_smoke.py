"""Existing-source refinement rejects invalid edits and rolls back exact weights."""
import argparse
import importlib
import json
import hashlib
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import bpy


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=root)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty test output directory.")
    output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(args.package_root.resolve().parent))
    package = importlib.import_module(args.package_root.name)
    package.register()
    try:
        api = importlib.import_module(f"{package.__name__}.implementations.canonical_rig_v2.head_refinement")
        bpy.ops.wm.open_mainfile(filepath=str(root / "example/v2/modular/StytchDoll/source.blend"), use_scripts=False)
        mesh, rig = bpy.data.objects["MeshvennScan"], bpy.data.objects["MeshvennCanonicalRig"]
        from scripts.author_stytch_doll import source_snapshot
        before = source_snapshot(mesh, rig)
        algorithm = mesh["meshvenn_rig_skinning_algorithm"]

        def rejected(call):
            try:
                call()
            except (ValueError, TypeError):
                return
            raise AssertionError("Invalid refinement was accepted.")

        mesh["meshvenn_source_mesh"] = mesh.name
        rejected(lambda: api.refine_head_weights(mesh))
        del mesh["meshvenn_source_mesh"]
        another = bpy.data.objects.new("HeadTestSharedMesh", mesh.data)
        try:
            rejected(lambda: api.refine_head_weights(mesh))
        finally:
            bpy.data.objects.remove(another)
        vertex = mesh.data.vertices[0]
        group = mesh.vertex_groups[vertex.groups[0].group]
        weight = vertex.groups[0].weight
        group.add((0,), weight*.5, "REPLACE")
        corrupted = source_snapshot(mesh, rig)
        rejected(lambda: api.refine_head_weights(mesh))
        assert source_snapshot(mesh, rig) == corrupted
        group.add((0,), weight, "REPLACE")
        assert source_snapshot(mesh, rig) == before
        # Inject a failure AFTER every weight has been applied. The rollback
        # must restore the original memberships/order/float32 values and props.
        with patch.object(api.json, "dumps", side_effect=RuntimeError("Injected post-write failure")):
            try:
                api.refine_head_weights(mesh)
            except RuntimeError as exc:
                assert "Injected" in str(exc)
            else:
                raise AssertionError("Failure injection was not reached.")
        assert source_snapshot(mesh, rig) == before
        assert mesh["meshvenn_rig_skinning_algorithm"] == algorithm and "meshvenn_head_isolation" not in mesh
        mesh.hide_set(False)
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.object.mode_set(mode="EDIT")
        rejected(lambda: api.refine_head_weights(mesh))
        bpy.ops.object.mode_set(mode="OBJECT")
        assert bpy.ops.bpt.refine_head_weights() == {"FINISHED"}
        assert not mesh.hide_get() and not mesh.hide_render
        previews = [obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH" and obj.get("meshvenn_source_mesh") == mesh.name]
        assert len(previews) == 5 and all(obj.hide_get() and obj.hide_render for obj in previews)
        after = source_snapshot(mesh, rig)
        assert before["weights"] != after["weights"]
        assert {k:v for k,v in before.items() if k != "weights"} == {k:v for k,v in after.items() if k != "weights"}
        rejected(lambda: api.refine_head_weights(mesh))
        assert source_snapshot(mesh, rig) == after
        report = json.loads(mesh["meshvenn_head_isolation"])
        assert report["changed_vertex_count"] == 2150 and report["native_rest_joints_unchanged"]
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
            selected_source = source_snapshot(mesh, rig)
            authority = hashlib.sha256(json.dumps(selected_source, sort_keys=True, allow_nan=False).encode()).hexdigest()
            assert authority == manifest["source_authority_sha256"]
            assert bpy.context.scene.bpt_settings.export_modular_manifest_path == "//authoring.json"
            rig.select_set(True)
            bpy.context.view_layer.objects.active = rig
            assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
            assert source_snapshot(mesh, rig) == selected_source
            runtime = importlib.import_module(f"{package.__name__}.operators.runtime")
            stages = importlib.import_module(f"{package.__name__}.core.pipeline_contracts")
            exported = runtime.get_last_pipeline_context(bpy.context.scene).require_output(stages.PipelineStage.EXPORT)
            roundtrip = exported.metadata["roundtrip"]["modular_character"]
            assert roundtrip["passed"]
            reader = importlib.import_module(f"{package.__name__}.implementations.glb_export.modular_gltf")
            document, binary = reader.read_glb(exported.path)
            reference, reference_binary = reader.read_glb(root / "example/v2/modular/StytchDoll/reference.glb")
            from scripts.workshop_doll_evidence import compare_head_variant
            proof = compare_head_variant(reference, reference_binary, document, binary,
                                         reader.read_accessor, manifest["glb_accessor_head_envelope"])
            assert proof["passed"] and not document.get("animations")
        (output / "report.json").write_text(json.dumps({"passed": True, "invalid_edits_rejected": True,
            "post_write_rollback_exact": True, "repeated_transfer_rejected": True,
            "relocated_variant_verified": bool(args.variant), "roundtrip": roundtrip,
            "refinement": report}, indent=2)+"\n", "utf-8")
        print("Head refinement PASS: exact rollback, safe rejection, source surface/atlas/rest joints preserved.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
