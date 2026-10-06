"""Exercise non-destructive partitions, corner fidelity and fail-closed preflight."""

from __future__ import annotations

import argparse
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys
import struct
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    root = args.package_root.resolve()
    sys.path.insert(0, str(root.parent))
    package = importlib.import_module(root.name)
    contracts = importlib.import_module(f"{package.__name__}.core.modular_character")
    partition = importlib.import_module(f"{package.__name__}.implementations.glb_export.modular_partition")
    fidelity = importlib.import_module(f"{package.__name__}.implementations.glb_export.modular_fidelity")
    metadata = importlib.import_module(f"{package.__name__}.implementations.glb_export.modular_metadata")
    normal_transport = importlib.import_module(f"{package.__name__}.implementations.glb_export.modular_normals")
    gltf = importlib.import_module(f"{package.__name__}.implementations.glb_export.modular_gltf")
    planning = importlib.import_module(f"{package.__name__}.implementations.glb_export.planning")
    exporter = importlib.import_module(f"{package.__name__}.implementations.glb_export.blender_export")
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    data = bpy.data.armatures.new("ModularTestRig")
    rig = bpy.data.objects.new("ModularTestRig", data)
    bpy.context.collection.objects.link(rig)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    bone = data.edit_bones.new("root")
    bone.head, bone.tail = (0, 0, 0), (0, 0, 1)
    hand = data.edit_bones.new("hand.L")
    hand.head, hand.tail, hand.parent = (0, 0, 1), (1, 0, 1), bone
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = bpy.data.meshes.new("ModularSourceMesh")
    mesh.from_pydata(((-0.5, 0, 0.5), (0.5, 0, 0.5), (0.5, 0, 1.5), (-0.5, 0, 1.5)), (), ((0, 1, 2), (0, 2, 3)))
    uv = mesh.uv_layers.new(name="AuthoredUV")
    color = mesh.color_attributes.new(name="AuthoredColor", type="FLOAT_COLOR", domain="CORNER")
    for loop in mesh.loops:
        uv.data[loop.index].uv = (0.15 + 0.12 * loop.index, 0.8 - 0.1 * loop.index)
        color.data[loop.index].color = (0.2 + 0.08 * loop.index, 0.3, 0.6, 1)
    mesh.color_attributes.active_color_index = 0
    mesh.color_attributes.render_color_index = 0
    normal = Vector((0.1, -1, 0.05)).normalized()
    mesh.normals_split_custom_set([normal] * len(mesh.loops))
    material = bpy.data.materials.new("AuthoredMaterial")
    material.use_nodes = True
    mesh.materials.append(material)
    source = bpy.data.objects.new("ModularSource", mesh)
    bpy.context.collection.objects.link(source)
    source.parent = rig
    source.matrix_world = (Matrix.Translation((0.3, 0.1, 0.2)) @ Matrix.Rotation(0.4, 4, "Z")
                           @ Matrix.Diagonal((1.3, 0.8, 1.1, 1)))
    source.vertex_groups.new(name="root").add(list(range(4)), 0.3, "REPLACE")
    source.vertex_groups.new(name="hand.L").add(list(range(4)), 0.7, "REPLACE")
    modifier = source.modifiers.new("CommonRig", "ARMATURE")
    modifier.object = rig
    signature = contracts.mesh_surface_sha256([tuple(vertex.co) for vertex in mesh.vertices],
                                              [tuple(face.vertices) for face in mesh.polygons])
    spec = contracts.ModularCharacterSpec(
        rig_id="canonical-biped-v2", rig_version=2,
        coordinates=contracts.CoordinateConvention(contracts.NormalizationConvention(False, None, 1)),
        regions=(contracts.RegionSpec("torso", "torso", "ModularTorso"), contracts.RegionSpec("hand", "left_hand", "ModularHand")),
        ownership={source.name: ("torso", "hand")}, ownership_source_sha256={source.name: signature},
        seams=contracts.SeamDeclarations(),
        sockets=(contracts.SocketSpec("grip", "left_grip", "hand.L", "hand", (0.2, 0.05, 0), (0, 0, 0, 1), (1, 1, 1)),),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    path = (args.output / "partition-fidelity.glb").resolve()
    plan = planning.GLBExportPlan(path, False, None, source, (source,),
                                  SimpleNamespace(implementation_id="canonical-biped-v2", armature_object=rig), rig, None, ())
    animation = rig.animation_data_create()
    animation.action = bpy.data.actions.new("UnrelatedUserAction")
    rig.pose.bones["root"].rotation_mode = "XYZ"
    rig.pose.bones["root"].rotation_euler.x = 0.15
    rig.pose.bones["root"].keyframe_insert(data_path="rotation_euler", frame=0)
    rig.pose.bones["root"].rotation_euler.x = 0.35
    rig.pose.bones["root"].keyframe_insert(data_path="rotation_euler", frame=30)
    animation.use_nla = True
    bpy.context.scene.frame_set(17, subframe=0.375)
    source.hide_render = True
    source.hide_select = True
    saved_pose = {bone.name: (bone.rotation_mode, bone.matrix_basis.copy()) for bone in rig.pose.bones}
    saved_action = animation.action
    baseline = (set(bpy.data.objects), set(bpy.data.meshes), signature, source.matrix_world.copy())
    expected = fidelity.capture_modular_expectation(plan, spec)
    assert bpy.context.scene.frame_current == 17 and bpy.context.scene.frame_subframe == 0.375
    assert animation.action is saved_action and animation.use_nla
    assert all(bone.rotation_mode == saved_pose[bone.name][0] and
               fidelity._matrix_error(bone.matrix_basis, saved_pose[bone.name][1]) < 1e-6
               for bone in rig.pose.bones)
    product_path = (args.output / "validated-product.glb").resolve()
    product_plan = replace(plan, path=product_path, overwrite_existing=True,
                           validate_roundtrip=True, modular_spec=spec)
    product_ui = exporter._capture_state(product_plan)
    product_data = (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.actions))
    product_report = {}
    exported = exporter.export_glb(product_plan, fidelity_report=product_report)
    assert exported.skin_count == 1 and product_report["modular_character"]["passed"]
    assert exporter._capture_state(product_plan) == product_ui
    assert product_data == (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.actions))
    published = product_path.read_bytes()
    with patch.object(fidelity, "validate_modular_roundtrip", side_effect=ValueError("Injected before publication")):
        try:
            exporter.export_glb(product_plan)
            raise AssertionError("Injected product validation failure was not raised")
        except ValueError as exc:
            assert "Injected before publication" in str(exc)
    assert product_path.read_bytes() == published
    assert not tuple(args.output.glob(".*.tmp.glb"))
    assert exporter._capture_state(product_plan) == product_ui
    assert product_data == (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.actions))
    previews = []
    with partition.prepare_modular_meshes(plan, spec) as prepared:
        for obj in prepared.mesh_objects:
            preview = obj.copy()
            bpy.context.collection.objects.link(preview)
            previews.append(preview)
    for preview, region in zip(previews, spec.regions):
        preview.name = region.node_name
    preview_snapshot = [(obj, obj.data, obj.matrix_world.copy(), obj.hide_render, obj.hide_get()) for obj in previews]
    try:
        preview_ui = exporter._capture_state(product_plan)
        exporter.export_glb(product_plan)
        final_document, _ = gltf.read_glb(product_path)
        assert {node["name"] for node in final_document["nodes"] if partition.REGION_ID_KEY in node.get("extras", {})} == {
            region.node_name for region in spec.regions}
        assert exporter._capture_state(product_plan) == preview_ui
        assert all(obj.data is mesh and obj.matrix_world == world and obj.hide_render == render and obj.hide_get() == hidden
                   for obj, mesh, world, render, hidden in preview_snapshot)
    finally:
        for obj in previews:
            preview_data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if preview_data.users == 0:
                bpy.data.meshes.remove(preview_data)
    published = product_path.read_bytes()
    provenance = SimpleNamespace(metadata={"normalized_height": False, "target_height": None,
                                          "normalization_scale": 1.0}, metrics={})
    for settings_metadata in ({"export_modular_character": True},
                              {"export_modular_spec": replace(spec, coordinates=contracts.CoordinateConvention(
                                  contracts.NormalizationConvention(True, 2, 1)))}):
        try:
            planning._modular_spec(SimpleNamespace(metadata=settings_metadata), (source,), plan.rig, provenance)
            raise AssertionError("Missing authoring JSON or contradictory normalization was accepted")
        except ValueError:
            pass
    assert product_path.read_bytes() == published
    with partition.prepare_modular_meshes(plan, spec) as prepared:
        assert len(prepared.mesh_objects) == 2
        assert sum(len(obj.data.polygons) for obj in prepared.mesh_objects) == 2
        for obj in prepared.mesh_objects:
            key = obj[partition.REGION_ID_KEY]
            assert len(obj.data.uv_layers) == len(mesh.uv_layers) == 1
            assert len(obj.data.color_attributes) == len(mesh.color_attributes) == 1
            assert fidelity._corner_error(expected["corners"][key], fidelity._corner_records(obj, {0}), 1e-6) <= fidelity.ATTRIBUTE_TOLERANCE
        with exporter._isolated_selection(prepared):
            result = bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                                               export_skins=True, export_animations=False, export_extras=True,
                                               export_attributes=True,
                                               export_vertex_color="ACTIVE", export_all_vertex_colors=True,
                                               export_rest_position_armature=True)
        assert "FINISHED" in result
        normal_transport.restore_modular_normals(path)
        metadata.embed_modular_metadata(path, spec)
        prepared.mesh_objects[0].hide_set(True)
        ui = exporter._capture_state(prepared)
        known_data = (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.actions))
        report = fidelity.validate_modular_roundtrip(prepared, spec, path, expected)
        assert report["passed"] and report["region_count"] == 2
        assert exporter._capture_state(prepared) == ui
        assert known_data == (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.actions))
        document, binary = gltf.read_glb(path)
        primitive = document["meshes"][0]["primitives"][0]
        for corruption in ("weights", "normal", "winding"):
            damaged = bytearray(binary)
            semantic = {"weights": "WEIGHTS_0", "normal": "NORMAL"}.get(corruption)
            accessor_index = primitive["attributes"][semantic] if semantic else primitive["indices"]
            accessor = document["accessors"][accessor_index]
            view = document["bufferViews"][accessor["bufferView"]]
            offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            if corruption == "weights":
                values = gltf.read_accessor(document, binary, accessor_index)[0]
                assert accessor["componentType"] == 5126
                struct.pack_into("<4f", damaged, offset, *(value * 2 for value in values))
            elif corruption == "normal":
                struct.pack_into("<3f", damaged, offset, 0, 0, 1)
            else:
                code, width = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}[accessor["componentType"]]
                indices = gltf.read_accessor(document, binary, accessor_index)
                stride = view.get("byteStride", width)
                struct.pack_into("<" + code, damaged, offset, indices[1][0])
                struct.pack_into("<" + code, damaged, offset + stride, indices[0][0])
            encoded = json.dumps(document, separators=(",", ":")).encode()
            encoded += b" " * (-len(encoded) % 4)
            damaged += b"\0" * (-len(damaged) % 4)
            body = struct.pack("<II", len(encoded), 0x4E4F534A) + encoded + struct.pack("<II", len(damaged), 0x004E4942) + damaged
            corrupt_path = args.output / f"corrupt-{corruption}.glb"
            corrupt_path.write_bytes(struct.pack("<4sII", b"glTF", 2, len(body) + 12) + body)
            try:
                fidelity.validate_modular_roundtrip(prepared, spec, corrupt_path, expected)
                raise AssertionError(f"Raw glTF {corruption} corruption passed validation")
            except ValueError:
                pass
            assert exporter._capture_state(prepared) == ui
            assert known_data == (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.actions))
        with patch.object(fidelity, "_region_samples", side_effect=ValueError("Injected fidelity failure")):
            try:
                fidelity.validate_modular_roundtrip(prepared, spec, path, expected)
                raise AssertionError("Injected validation failure was not raised")
            except ValueError as exc:
                assert "Injected fidelity" in str(exc)
        assert exporter._capture_state(prepared) == ui
        assert known_data == (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.actions))
    assert set(bpy.data.objects) == baseline[0] and set(bpy.data.meshes) == baseline[1]
    assert source.matrix_world == baseline[3]
    assert source.hide_render and source.hide_select
    assert bpy.context.scene.frame_current == 17 and bpy.context.scene.frame_subframe == 0.375
    assert animation.action is saved_action and animation.use_nla
    assert all(bone.rotation_mode == saved_pose[bone.name][0] and
               fidelity._matrix_error(bone.matrix_basis, saved_pose[bone.name][1]) < 1e-6
               for bone in rig.pose.bones)
    assert contracts.mesh_surface_sha256([tuple(vertex.co) for vertex in mesh.vertices],
                                         [tuple(face.vertices) for face in mesh.polygons]) == signature
    for mutation in ("stale", "shape", "modifier", "rollback"):
        changed = spec
        if mutation == "stale":
            changed = replace(spec, ownership_source_sha256={source.name: "0" * 64})
        elif mutation == "shape":
            source.shape_key_add(name="Basis")
        elif mutation == "modifier":
            extra = source.modifiers.new("UnsupportedSubdivision", "SUBSURF")
        try:
            with partition.prepare_modular_meshes(plan, changed):
                if mutation == "rollback":
                    raise ValueError("Injected downstream validation failure")
                raise AssertionError(f"Failed to reject {mutation}")
        except ValueError:
            pass
        finally:
            if mutation == "shape":
                source.shape_key_clear()
            elif mutation == "modifier":
                source.modifiers.remove(extra)
        assert set(bpy.data.objects) == baseline[0] and set(bpy.data.meshes) == baseline[1]
    print("Modular partition/fidelity smoke: PASS", report)


if __name__ == "__main__":
    main()
