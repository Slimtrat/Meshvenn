"""Render actual imported modular GLB states; never substitute cached previews."""
from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from scripts.render_turntable import clear_scene, combined_bounds, create_camera, look_at, setup_lighting, setup_render
from scripts.v2_preview_evidence import IMAGE_NAMES, digest, read_json, validate_revision
from scripts.v2_preview_appearance import verify_appearance


def _module(name):
    return importlib.import_module(f"{ROOT.name}.{name}")


def _positions(meshes):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return {obj.name: tuple(tuple(obj.matrix_world @ vertex.co) for vertex in
                           obj.evaluated_get(depsgraph).data.vertices) for obj in meshes}


def _import(path):
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    # glTF's Blender importer also creates hidden custom-bone display widgets.
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and not obj.hide_render
              and any(not collection.hide_render for collection in obj.users_collection)]
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not meshes:
        raise AssertionError("The preview GLB has no meshes.")
    return meshes, rigs


def _camera(meshes, size, samples):
    lower, upper = combined_bounds(meshes)
    target, dimensions = (lower + upper) * .5, upper - lower
    camera = create_camera(target=target, model_size=dimensions)
    radius = max(dimensions)
    camera.location = target + Vector((radius * 1.5, -radius * 2.6, radius * .35))
    look_at(camera, target)
    setup_lighting(dimensions)
    # Move the existing neutral lighting rig around this unchanged character.
    for obj in bpy.context.scene.objects:
        if obj.type == "LIGHT":
            obj.location += target
            obj.data.energy *= max(radius, 1) ** 2
            look_at(obj, target)
    setup_render(size=size, samples=samples)
    return camera


def _render(path):
    bpy.context.scene.render.filepath = str(path.resolve())
    bpy.ops.render.render(write_still=True)
    if not path.is_file():
        raise AssertionError("Preview render did not create its PNG.")


def _joint_world(document):
    node_matrix = _module("implementations.glb_export.modular_fidelity")._node_matrix
    nodes, parents, matrices = document["nodes"], {}, {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            if child in parents:
                raise ValueError("Preview GLB has multiply-parented nodes.")
            parents[child] = index

    def world(index, active=()):
        if index in active or not 0 <= index < len(nodes):
            raise ValueError("Invalid or cyclic preview joint binding.")
        if index not in matrices:
            local = node_matrix(nodes[index])
            matrices[index] = world(parents[index], (*active, index)) @ local if index in parents else local
        return matrices[index]

    return world


def _socket_positions(rig, envelope, world):
    axes = _module("implementations.glb_export.modular_fidelity")._AXES
    result = {}
    for socket in envelope["spec"]["sockets"]:
        bone = rig.pose.bones[socket["parent_bone"]]
        rest = rig.matrix_world @ bone.bone.matrix_local
        pose = rig.matrix_world @ bone.matrix
        delta = axes @ pose @ rest.inverted() @ axes.inverted()
        rotation = socket["rotation"]
        local = Matrix.LocRotScale(Vector(socket["translation"]),
                                  Quaternion((rotation[3], *rotation[:3])), Vector(socket["scale"]))
        raw_rest = world(envelope["bindings"]["joint_nodes"][socket["parent_bone"]])
        result[socket["id"]] = axes.inverted() @ delta @ raw_rest @ local
    return result


def _markers(matrices):
    """Diagnostic-only spheres: not objects added to the delivered GLB."""
    material = bpy.data.materials.new("V2_socket_diagnostic")
    material.diffuse_color = (1, .25, .015, 1)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = material.diffuse_color
    shader.inputs["Emission Color"].default_value = material.diffuse_color
    shader.inputs["Emission Strength"].default_value = 1.5
    collection = bpy.data.collections.new("V2 Diagnostic Sockets")
    bpy.context.scene.collection.children.link(collection)
    markers = []
    for name, matrix in matrices.items():
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=.028,
                                          location=matrix.translation)
        marker = bpy.context.object
        # glTF bone-shape creation can leave a hidden collection active.
        for previous in tuple(marker.users_collection):
            previous.objects.unlink(marker)
        collection.objects.link(marker)
        marker.name = f"Diagnostic_{name}"
        marker.data.materials.append(material)
        markers.append(marker)
    return markers


def _socket_render(meshes, matrices, path):
    """Explicit X-ray diagnostic, separate from the unchanged textured renders."""
    material = bpy.data.materials.new("V2_socket_xray_body")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (.32, .42, .55, 1)
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = .15
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(shader.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes.get("Material Output").inputs["Surface"])
    original = {obj: tuple(obj.data.materials) for obj in meshes}
    markers = _markers(matrices)
    try:
        for obj in meshes:
            for index in range(len(obj.data.materials)):
                obj.data.materials[index] = material
        _render(path)
    finally:
        for obj, materials in original.items():
            for index, previous in enumerate(materials):
                obj.data.materials[index] = previous
        for marker in markers:
            bpy.data.objects.remove(marker, do_unlink=True)


def _select_clip(rig, document):
    names = [item.get("name", "") for item in document.get("animations", [])]
    chosen = next((name for name in names if name.rsplit(".", 1)[0].removeprefix("Meshvenn_") == "Walk_Loop"), None)
    if chosen is None:
        raise AssertionError("The fixture no longer contains the measured Walk_Loop animation.")
    animation = rig.animation_data
    tracks = [track for track in animation.nla_tracks if track.name == chosen]
    if len(tracks) != 1 or len(tracks[0].strips) != 1:
        raise AssertionError("Imported preview lost the selected animation.")
    animation.use_nla = False
    animation.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    animation.action = tracks[0].strips[0].action
    return chosen, animation.action


def render_bundle(directory: Path, output: Path, *, sha: str, run_id: str, attempt: str,
                  size: int = 512, samples: int = 32) -> dict:
    validate_revision(sha)
    fixture = directory / "modular_character"
    manifest = read_json(fixture / "manifest.json")
    verify_appearance(manifest)
    glb = fixture / "character.glb"
    if (digest(glb) != manifest["sha256"] or digest(fixture / "source.blend") != manifest["editable_source_sha256"]
            or manifest["roundtrip"].get("passed") is not True):
        raise AssertionError("Modular preview input is not the certified generated fixture.")
    document, _ = _module("implementations.glb_export.modular_gltf").read_glb(glb)
    envelope = document["asset"]["extras"]["meshvenn_modular_character"]
    if envelope != manifest["contract"]:
        raise AssertionError("Preview contract differs from the rendered GLB.")
    output.mkdir(parents=True, exist_ok=True)
    source = fixture / "reference_unrigged.glb"
    meshes, rigs = _import(source)
    if rigs or any(obj.vertex_groups for obj in meshes):
        raise AssertionError("Rendered source reference retained a rig or weights.")
    _camera(meshes, size, samples)
    _render(output / "source.png")
    meshes, rigs = _import(glb)
    if len(rigs) != 1 or len(rigs[0].data.bones) != 18 or len(meshes) != len(envelope["spec"]["regions"]):
        raise AssertionError("Preview did not import the modular fixture's native shared rig.")
    if {obj.name for obj in meshes} != {region["node_name"] for region in envelope["spec"]["regions"]}:
        raise AssertionError("Preview imported a different modular mesh inventory.")
    rig = rigs[0]
    rig.data.pose_position = "REST"
    bpy.context.view_layer.update()
    rest = _positions(meshes)
    _camera(meshes, size, samples)
    _render(output / "rest.png")
    raw_world = _joint_world(document)
    # In REST position, pose matrices can still contain the importer's active clip.
    rig.animation_data.use_nla = False
    rig.animation_data.action = None
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    bpy.context.view_layer.update()
    sockets_rest = _socket_positions(rig, envelope, raw_world)
    _socket_render(meshes, sockets_rest, output / "sockets_rest.png")
    rig.data.pose_position = "POSE"
    clip_name, action = _select_clip(rig, document)
    start, end = map(float, action.frame_range)
    if end <= start:
        raise AssertionError("Preview clip has no duration.")
    # Select the most informative actual frame, not a hand-authored replacement pose.
    best_error, best_frame = -1.0, start
    for index in range(9):
        frame = start + (end - start) * index / 8
        bpy.context.scene.frame_set(math.floor(frame), subframe=frame % 1)
        positions = _positions(meshes)
        error = max(math.dist(a, b) for name in rest for a, b in zip(rest[name], positions[name]))
        if error > best_error:
            best_error, best_frame = error, frame
    if best_error <= .001:
        raise AssertionError("The actual imported preview animation did not deform the skin.")
    bpy.context.scene.frame_set(math.floor(best_frame), subframe=best_frame % 1)
    _render(output / "pose.png")
    hidden = next(region for region in envelope["spec"]["regions"] if region["role"] == "left-arm")
    obj = next(obj for obj in meshes if obj.name == hidden["node_name"])
    obj.hide_render = True
    _render(output / "hidden.png")
    obj.hide_render = False
    sockets_pose = _socket_positions(rig, envelope, raw_world)
    _socket_render(meshes, sockets_pose, output / "sockets_pose.png")
    socket_motion = max((sockets_pose[name].translation - value.translation).length
                        for name, value in sockets_rest.items())
    reports = [read_json(directory / f"{name}_character_organic" / "report.json")
               for name in ("quaternius_human", "quaternius_ual1")]
    if digest(glb) != manifest["sha256"] or digest(fixture / "source.blend") != manifest["editable_source_sha256"]:
        raise AssertionError("Preview rendering altered a certified delivery artifact.")
    report = {"schema_version": 1, "source_sha": sha, "run_id": str(run_id), "run_attempt": str(attempt),
              "rendered_from_final_glb": True, "renderer": {"blender": bpy.app.version_string,
              "engine": "CYCLES CPU", "size": size, "samples": samples}, "modular": manifest,
              "source_reference_sha256": digest(source), "images": {name: digest(output / name) for name in IMAGE_NAMES},
              "pose": {"clip_name": clip_name, "frame": best_frame, "maximum_deformation_m": best_error,
                       "maximum_socket_motion_m": socket_motion, "hidden_region_id": hidden["id"]},
              "reconstruction": reports}
    (output / "preview.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", "utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", default="1")
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--samples", type=int, default=32)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if not 128 <= args.size <= 1024 or not 1 <= args.samples <= 64:
        raise ValueError("Preview rendering budget exceeded.")
    render_bundle(args.evidence.resolve(), args.output.resolve(), sha=args.source_sha,
                  run_id=args.run_id, attempt=args.run_attempt, size=args.size, samples=args.samples)


if __name__ == "__main__":
    main()
