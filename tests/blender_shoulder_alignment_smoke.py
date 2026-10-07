"""Actual static doll: rest-only two-pivot edit, exact rollback and sockets."""
import argparse
from dataclasses import replace
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
    parser.add_argument("--package-root",type=Path,default=repository)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--variant",type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    root,output = args.package_root.resolve(),args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty verification output directory.")
    sys.path.insert(0,str(root.parent))
    sys.path.insert(0,str(repository))
    package = importlib.import_module(root.name)
    package.register()
    def module(name):
        return importlib.import_module(root.name+"."+name)
    try:
        bpy.ops.wm.open_mainfile(filepath=str(repository / "example/v2/modular/StytchDollAuthoredSkin/source.blend"),use_scripts=False)
        mesh,rig = bpy.data.objects["MeshvennScan"],bpy.data.objects["MeshvennCanonicalRig"]
        spec = module("implementations.glb_export.face_authoring")._read(repository / "example/v2/modular/StytchDollAuthoredSkin/authoring.json")
        api = module("implementations.canonical_rig_v2.shoulder_alignment")
        from scripts.author_stytch_doll import source_snapshot
        before = source_snapshot(mesh,rig)
        original,properties = rig.data,dict(mesh.items())
        objects,armatures = set(bpy.data.objects),set(bpy.data.armatures)
        def rejected(call):
            try:
                call()
            except (TypeError,ValueError):
                return
            raise AssertionError("Unsafe shoulder rest edit accepted.")
        def perform():
            with api.align_authored_shoulders(mesh,spec):
                pass
        shared = bpy.data.objects.new("ShoulderSharedRigTest",rig.data)
        try:
            rejected(perform)
        finally:
            bpy.data.objects.remove(shared)
        moved_socket = replace(spec.sockets[0],parent_bone="upper_arm.L")
        bad_spec = replace(spec,sockets=(moved_socket,*spec.sockets[1:]))
        def bad_socket():
            with api.align_authored_shoulders(mesh,bad_spec):
                pass
        rejected(bad_socket)
        action = bpy.data.actions.new("ShoulderNoImplicitMotionMigration")
        rig.animation_data_create().action = action
        try:
            rejected(perform)
        finally:
            rig.animation_data_clear()
            bpy.data.actions.remove(action)
        rig.pose.bones["head"].rotation_mode = "XYZ"
        rig.pose.bones["head"].rotation_euler.x = .1
        rejected(perform)
        rig.pose.bones["head"].matrix_basis.identity()
        bpy.context.view_layer.update()
        with patch.object(api.json,"dumps",side_effect=RuntimeError("Injected metadata failure")):
            try:
                perform()
            except RuntimeError as exc:
                assert "Injected" in str(exc)
            else:
                raise AssertionError("Failure injection missed.")
        assert rig.data is original and source_snapshot(mesh,rig) == before
        assert dict(mesh.items()) == properties
        assert set(bpy.data.objects) == objects and set(bpy.data.armatures) == armatures
        try:
            with api.align_authored_shoulders(mesh,spec):
                raise RuntimeError("Injected caller failure")
        except RuntimeError:
            pass
        assert rig.data is original and source_snapshot(mesh,rig) == before
        assert set(bpy.data.objects) == objects and set(bpy.data.armatures) == armatures
        mesh.hide_set(False)
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        assert bpy.ops.bpt.align_authored_shoulders() == {"FINISHED"}
        after = source_snapshot(mesh,rig)
        assert {k:v for k,v in before.items() if k != "bones"} == {k:v for k,v in after.items() if k != "bones"}
        assert rig.data is not original and original.name in bpy.data.armatures
        assert spec.to_dict() == module("implementations.glb_export.face_authoring")._read(repository / "example/v2/modular/StytchDollAuthoredSkin/authoring.json").to_dict()
        from mathutils import Matrix
        for socket in spec.sockets:
            previous = Matrix(before["bones"][socket.parent_bone]["matrix"])
            current = rig.data.bones[socket.parent_bone].matrix_local
            error = max(abs(a-b) for ra,rb in zip(previous,current) for a,b in zip(ra,rb))
            assert error < 2e-4, (socket.id,error)  # Existing native matrix proof tolerance, unchanged.
        rejected(perform)
        assert source_snapshot(mesh,rig) == after
        output.mkdir(parents=True,exist_ok=True)
        settings = bpy.context.scene.bpt_settings
        settings.export_modular_manifest_path = str(repository / "example/v2/modular/StytchDollAuthoredSkin/authoring.json")
        settings.export_output_path = str(output / "aligned.glb")
        assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
        assert source_snapshot(mesh,rig) == after
        pipeline = module("operators.runtime").get_last_pipeline_context(bpy.context.scene)
        result = pipeline.require_output(module("core.pipeline_contracts").PipelineStage.EXPORT)
        assert result.metadata["roundtrip"]["modular_character"]["passed"] and not result.animation_names
        relocated_proof = None
        if args.variant:
            variant = args.variant.resolve(strict=True)
            relocated = output / "relocated"
            relocated.mkdir()
            for name in ("source.blend","authoring.json"):
                shutil.copy2(variant / name,relocated / name)
            bpy.ops.wm.open_mainfile(filepath=str(relocated / "source.blend"),use_scripts=False)
            mesh,rig = bpy.data.objects["MeshvennScan"],bpy.data.objects["MeshvennCanonicalRig"]
            selected = source_snapshot(mesh,rig)
            bpy.context.scene.bpt_settings.export_output_path = "//reexport.glb"
            assert bpy.ops.bpt.export_existing_modular_source() == {"FINISHED"}
            assert source_snapshot(mesh,rig) == selected
            pipeline = module("operators.runtime").get_last_pipeline_context(bpy.context.scene)
            result = pipeline.require_output(module("core.pipeline_contracts").PipelineStage.EXPORT)
            reader = module("implementations.glb_export.modular_gltf")
            from scripts.workshop_doll_evidence import compare_reference
            old,old_binary = reader.read_glb(variant / "character.glb")
            new,new_binary = reader.read_glb(result.path)
            relocated_proof = compare_reference(old,old_binary,new,new_binary,reader.read_accessor)
            assert relocated_proof["max_weight_error"] == relocated_proof["max_inverse_bind_error"] == 0
        (output / "report.json").write_text(json.dumps({"passed":True,"exact_rollback":True,
            "surface_weights_materials_preserved":True,"socket_parent_frames_preserved":True,
            "edit":json.loads(mesh["meshvenn_shoulder_alignment"]),"relocated_proof":relocated_proof},indent=2),"utf-8")
        print("Shoulder alignment PASS: exact rollback, two observed origins, unchanged surface/skin/sockets, guarded export.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
