"""Re-export the pinned workshop doll's explicit source-owned regions, without rebuild."""
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
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
SOURCE_GLB_SHA256 = "169ec90b326ccb71c1868dc26e7676e80a53990e9906a6ab4d23af04118d2034"
SOURCE_BLEND_SHA256 = "a41de571fb385502ea1c14f6a296348312491e59de439d97880eb47c41f06680"
SOURCE_SURFACE_SHA256 = "4f18119c54fe408c8c6ca8859c5f7f56bf96a77b57d36ffb472ad6e83fb307ad"
SOURCE_REVISION = "47cd554510c6229fe01a8b56cb16660f846a1ed2"
REGIONS = ("body-core", "left-arm", "right-arm", "left-leg", "right-leg")
SOCKETS = {"head": ("head", "body-core"), "left-arm": ("hand.L", "left-arm"),
           "right-arm": ("hand.R", "right-arm"), "left-leg": ("foot.L", "left-leg"),
           "right-leg": ("foot.R", "right-leg"), "back": ("chest", "body-core"),
           "backpack": ("spine", "body-core"), "wing": ("chest", "body-core")}


def module(name):
    return importlib.import_module(f"{ROOT.name}.{name}")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", "utf-8")


def source_snapshot(mesh, armature):
    """Exact retained-authority check, separate from toleranced GLB transport."""
    # Resolve loaded dependency-graph caches before taking either snapshot.
    bpy.context.view_layer.update()
    from array import array
    pixel_hashes = {}
    for material in mesh.data.materials:
        for node in material.node_tree.nodes if material and material.use_nodes else ():
            image = getattr(node, "image", None)
            if image is not None:
                pixels = array("f", [0.0]) * len(image.pixels)
                image.pixels.foreach_get(pixels)
                pixel_hashes[image.name] = hashlib.sha256(pixels.tobytes()).hexdigest()
    return {"surface": module("core.modular_character").mesh_surface_sha256(
        [tuple(vertex.co) for vertex in mesh.data.vertices], [tuple(face.vertices) for face in mesh.data.polygons]),
        "world": [list(row) for row in mesh.matrix_world],
        "groups": [(group.name, group.index) for group in mesh.vertex_groups],
        "weights": [[(group.group, group.weight) for group in vertex.groups] for vertex in mesh.data.vertices],
        "uv": {layer.name: [tuple(item.uv) for item in layer.data] for layer in mesh.data.uv_layers},
        "normals": [tuple(item.vector) for item in mesh.data.corner_normals],
        "colors": {layer.name: [tuple(item.color) for item in layer.data] for layer in mesh.data.color_attributes},
        "face_materials": [face.material_index for face in mesh.data.polygons],
        "material_signatures": sorted(module("implementations.glb_export.fidelity_samples").material_signatures((mesh,))),
        "material_pixels": pixel_hashes,
        "rig_world": [list(row) for row in armature.matrix_world],
        "bones": {bone.name: {"parent": bone.parent.name if bone.parent else None,
                               "matrix": [list(row) for row in bone.matrix_local],
                               "head": tuple(bone.head_local), "tail": tuple(bone.tail_local)}
                  for bone in armature.data.bones}}


def assert_source_unchanged(before, after, diagnostic_directory):
    if before != after:
        changed = [key for key in before if before[key] != after[key]]
        write_json(Path(diagnostic_directory) / "source-change-diagnostic.json",
                   {"changed_fields": changed, "before": before, "after": after})
        raise AssertionError("No Rebuild changed selected source authority: " + ", ".join(changed))


def author_spec(mesh, plan, reference):
    """Replay frozen polygon/vertex choices, never rerun a geometric classifier."""
    contract = module("core.modular_character")
    fingerprint = contract.mesh_surface_sha256([tuple(v.co) for v in mesh.data.vertices],
                                                [tuple(f.vertices) for f in mesh.data.polygons])
    if (fingerprint != SOURCE_SURFACE_SHA256 or plan["source_surface_sha256"] != fingerprint
            or plan["source_object"] != mesh.name or plan["schema_version"] != 1):
        raise ValueError("This authoring only applies to the exact pinned workshop doll surface.")
    if set(plan["selections"]) != set(REGIONS) - {"body-core"}:
        raise ValueError("Missing or ambiguous authored limb selections.")
    owners, used = ["body-core"] * len(mesh.data.polygons), set()
    for role, selection in plan["selections"].items():
        for index in selection["polygon_indices"]:
            if type(index) is not int or not 0 <= index < len(owners) or index in used:
                raise ValueError("Invalid or duplicated authored polygon index.")
            used.add(index)
            owners[index] = role
    reader = module("implementations.glb_export.modular_gltf")
    document, _ = reader.read_glb(reference)
    from scripts.render_v2_pipeline_preview import _joint_world
    world = _joint_world(document)
    joints = {document["nodes"][index]["name"]: index for index in document["skins"][0]["joints"]}
    axes = module("implementations.glb_export.modular_fidelity")._AXES
    anchors, sockets = [], []
    if {item["role"] for item in plan["socket_landmarks"]} != set(SOCKETS) or len(plan["socket_landmarks"]) != 8:
        raise ValueError("The workshop doll requires eight uniquely authored landmarks.")
    for landmark in plan["socket_landmarks"]:
        role, index = landmark["role"], landmark["vertex_index"]
        if type(index) is not int or not 0 <= index < len(mesh.data.vertices):
            raise ValueError("Socket landmark does not name a source vertex.")
        bone, region = SOCKETS[role]
        point = axes @ mesh.matrix_world @ mesh.data.vertices[index].co
        parent = world(joints[bone])
        rotation = landmark["world_rotation_xyzw"]
        orientation = Quaternion((rotation[3], *rotation[:3]))
        if abs(orientation.magnitude - 1) > 1e-6:
            raise ValueError("Authored socket orientation must be normalized.")
        # Preserve inherited native normalization. These markers do NOT cancel
        # the rig's ancestor scale or manufacture a different equipment frame.
        desired = Matrix.LocRotScale(point, orientation, parent.to_scale())
        translation, local_rotation, scale = (parent.inverted() @ desired).decompose()
        local_rotation.normalize()
        socket = contract.SocketSpec("attach-" + role, role, bone, region, tuple(translation),
                                     (local_rotation.x, local_rotation.y, local_rotation.z, local_rotation.w), tuple(scale))
        sockets.append(socket)
        anchors.append({"socket_id": socket.id, "source_vertex_index": index,
                        "authored_gltf_world_matrix": [list(row) for row in desired]})
    spec = contract.ModularCharacterSpec(
        rig_id="canonical-biped-v2", rig_version=2,
        coordinates=contract.CoordinateConvention(contract.NormalizationConvention(
            mesh["bpt_normalize_height"], mesh["bpt_target_height"], mesh["meshvenn_normalization_scale"])),
        regions=tuple(contract.RegionSpec(role, role, "Doll_" + role.replace("-", "_")) for role in REGIONS),
        ownership={mesh.name: tuple(owners)}, ownership_source_sha256={mesh.name: fingerprint},
        seams=contract.SeamDeclarations(), sockets=tuple(sockets))
    return spec, anchors


def remove_saved_previews(mesh, spec):
    """Replace only identified disposable previews in this in-memory source copy."""
    partition = module("implementations.glb_export.modular_partition")
    regions = {region.id: region for region in spec.regions}
    previews = [obj for obj in bpy.context.scene.objects
                if obj.get(partition.SOURCE_MESH_KEY) == mesh.name]
    for obj in previews:
        region = regions.get(obj.get(partition.REGION_ID_KEY))
        if (region is None or obj.type != "MESH" or obj.name != region.node_name
                or obj.get(partition.REGION_ROLE_KEY) != region.role
                or obj.get(partition.SEAM_POLICY_KEY) != partition.SEAM_POLICY):
            raise ValueError("Unrecognized saved preview; review the scene instead of overwriting it.")
    for obj in previews:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data.users == 0:
            bpy.data.meshes.remove(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    fixture = ROOT / "example/v2/modular/StytchDoll"
    parser.add_argument("--input-source", type=Path, default=fixture / "source.blend")
    parser.add_argument("--reference-glb", type=Path, default=fixture / "reference.glb")
    parser.add_argument("--partition-authoring", type=Path, default=fixture / "partition-authoring.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    source, reference, output = args.input_source.resolve(strict=True), args.reference_glb.resolve(strict=True), args.output.resolve()
    if digest(reference) != SOURCE_GLB_SHA256:
        raise ValueError("The full-body reference is not the pinned native workshop doll.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory; no source or artifact is overwritten.")
    output.mkdir(parents=True, exist_ok=True)
    plan = module("core.modular_character.json_io").strict_json_loads(args.partition_authoring.read_text("utf-8"))
    package = importlib.import_module(ROOT.name)
    package.register()
    try:
        bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False)
        mesh = bpy.context.scene.objects.get(plan["source_object"])
        if mesh is None or mesh.type != "MESH":
            raise ValueError("Missing exact authoritative workshop doll mesh.")
        armature = next(modifier.object for modifier in mesh.modifiers if modifier.type == "ARMATURE")
        before = source_snapshot(mesh, armature)
        spec, anchors = author_spec(mesh, plan, reference)
        remove_saved_previews(mesh, spec)
        write_json(output / "authoring.json", spec.to_dict())
        shutil.copy2(args.partition_authoring, output / "partition-authoring.json")
        shutil.copy2(reference, output / "reference.glb")
        settings = bpy.context.scene.bpt_settings
        settings.export_modular_character = True
        settings.export_modular_manifest_path = str(output / "authoring.json")
        settings.export_output_path = str(output / "character.glb")
        settings.export_overwrite_existing = False
        bpy.ops.object.select_all(action="DESELECT")
        mesh.hide_set(False)
        mesh.hide_render = False
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        editor = module("implementations.glb_export.face_authoring")
        editor.load_face_ownership(mesh, spec, replace_existing=editor.STATE_KEY in mesh)
        # Use the same public selection operation as the editor, not a private
        # consumer partitioner. Replaying all five lists must reproduce the JSON.
        for region in spec.regions:
            for face, owner in zip(mesh.data.polygons, spec.ownership[mesh.name]):
                face.select = owner == region.id
            assert bpy.ops.bpt.assign_modular_faces(region_id=region.id) == {"FINISHED"}
        assert bpy.ops.bpt.save_modular_face_ownership(overwrite=True) == {"FINISHED"}
        initialized = module("implementations.glb_export.modular_source").CATALOGUE_REFERENCE in mesh
        forbidden = (("implementations.projection_images", "ProjectionImagesImplementation"),
                     ("implementations.native_visual_hull", "NativeVisualHullImplementation"),
                     ("implementations.uv_bake", "UVBakeImplementation"),
                     ("implementations.canonical_rig_v2", "CanonicalRigV2Implementation"),
                     ("implementations.canonical_motion", "CanonicalMotionRetargetImplementation"))
        with ExitStack() as guards:
            for module_name, class_name in forbidden:
                implementation = getattr(module(module_name), class_name)
                guards.enter_context(patch.object(implementation, "execute", side_effect=AssertionError("No Rebuild stage was executed.")))
            result = bpy.ops.bpt.export_existing_modular_source(
                initialize_static_source=not initialized,
                binding_method="canonical-envelope-v2" if not initialized else "")
        if result != {"FINISHED"}:
            raise AssertionError("The exact workshop doll did not pass product No Rebuild export.")
        context = module("operators.runtime").get_last_pipeline_context(bpy.context.scene)
        stage = module("core.pipeline_contracts").PipelineStage
        exported = context.require_output(stage.EXPORT)
        after = source_snapshot(mesh, armature)
        assert_source_unchanged(before, after, output)
        document, _ = module("implementations.glb_export.modular_gltf").read_glb(exported.path)
        envelope = document["asset"]["extras"]["meshvenn_modular_character"]
        from scripts.workshop_doll_evidence import compare_reference
        reader = module("implementations.glb_export.modular_gltf")
        reference_document, reference_binary = reader.read_glb(reference)
        _, candidate_binary = reader.read_glb(exported.path)
        reference_proof = compare_reference(reference_document, reference_binary, document, candidate_binary, reader.read_accessor)
        triangle_count = sum(document["accessors"][primitive["indices"]]["count"] // 3
                             for item in document["meshes"] for primitive in item["primitives"])
        assert triangle_count == 14252 and triangle_count <= 18000
        assert len(document["meshes"]) == 5 and len(document["skins"][0]["joints"]) == 18
        assert not document.get("animations")
        # Store packed portability without changing the baked atlas or source.
        for index, image in enumerate(bpy.data.images):
            if image.packed_file is not None or image.source == "FILE":
                if image.packed_file is None:
                    image.pack()
                image.filepath_raw = f"//packed/image-{index}.png"
                for packed in image.packed_files:
                    packed.filepath = image.filepath_raw
                image.use_fake_user = True
        settings.export_modular_manifest_path = "//authoring.json"
        settings.export_output_path = "//character.glb"
        # This is preview construction, not a second publication. Temporarily
        # allow the already validated destination during plan resolution only.
        previous_overwrite = context.metadata["export_overwrite_existing"]
        try:
            context.metadata["export_overwrite_existing"] = True
            plan_export = module("implementations.glb_export.planning").build_export_plan(context)
        finally:
            context.metadata["export_overwrite_existing"] = previous_overwrite
        with module("implementations.glb_export.modular_partition").prepare_modular_meshes(plan_export, spec) as preview:
            mesh.hide_set(True)
            mesh.hide_render = True
            assert {obj.name for obj in preview.mesh_objects} == {region.node_name for region in spec.regions}
            assert all(not obj.hide_render and not obj.hide_get() for obj in preview.mesh_objects)
            assert len([obj for obj in bpy.context.scene.objects if obj.type == "MESH"]) == 6
            bpy.ops.wm.save_as_mainfile(filepath=str(output / "source.blend"), compress=True, relative_remap=False)
        native_provenance = {
            "repository": "Stytch0/Stytch", "revision": SOURCE_REVISION,
            "path": "godot/Stytch.GodotHost/Assets/Embodiment/Candidates/MeshVennV2/",
            "source_glb_sha256": SOURCE_GLB_SHA256, "original_blend_sha256": SOURCE_BLEND_SHA256,
            "meshvenn_generation_revision": "541986da530c28543f342b50a23fac3dfb771fbc",
            "meshvenn_release": "v0.1.175", "native_build_run": 37456362607,
            "publication": "Source owner explicitly authorized publication of the complete doll bundle in Meshvenn."}
        samples = mesh["meshvenn_uv_bake_surface_samples"]
        fallbacks = mesh["meshvenn_uv_bake_fallback_samples"]
        manifest = {"schema_version": 1, "source_asset": "stytch_workshop_doll",
                    "artifact": "character.glb", "sha256": exported.sha256,
                    "editable_source": "source.blend", "editable_source_sha256": digest(output / "source.blend"),
                    "reference": "reference.glb", "authoring": "authoring.json", "contract": envelope,
                    "source_provenance": native_provenance, "native_joint_count": 18, "animation_count": 0,
                    "source_polygon_count": len(mesh.data.polygons), "triangle_count": triangle_count,
                    "triangle_budget": 18000, "pipeline": "existing native source -> explicit whole-face ownership -> No Rebuild modular export",
                    "source_authority_unchanged": True, "no_rebuild_verified": True,
                    "reference_fidelity": reference_proof,
                    "source_authority_sha256": hashlib.sha256(json.dumps(before, sort_keys=True, allow_nan=False).encode()).hexdigest(),
                    "surface_refinement": json.loads(mesh["bpt_surface_refinement"]),
                    "regions": {role: spec.ownership[mesh.name].count(role) for role in REGIONS},
                    "socket_authoring": anchors, "roundtrip": exported.metadata["roundtrip"]["modular_character"],
                    "appearance": {"regenerated": False, "full_appearance_qualified": False, "input_view_count": 2,
                                   "surface_samples": samples, "neutral_fallback_samples": fallbacks,
                                   "neutral_fallback_ratio": fallbacks / samples,
                                   "uv_overlap_pixels": mesh["meshvenn_uv_bake_overlap_pixels"],
                                   "scope": "Original source bake preserved, including missing coverage and its reported UV overlap; no overlay or invented views."},
                    "consumer_acceptance": "Godot/Stytch replay, gameplay and mobile gates remain downstream and are not claimed here."}
        write_json(output / "manifest.json", manifest)
        print(f"Workshop doll PASS: 5 regions, 8 authored sockets, 18 unchanged joints, {triangle_count} triangles; no rebuild.")
    finally:
        package.unregister()


if __name__ == "__main__":
    main()
