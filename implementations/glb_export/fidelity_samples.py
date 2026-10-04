"""Deterministic Blender observations used by GLB round-trip validation."""

from __future__ import annotations

from contextlib import contextmanager
import math

import bpy
from mathutils import Matrix


def animated_ids(meshes, armature, auxiliary_objects=()):
    objects = (*meshes, *((armature,) if armature is not None else ()), *auxiliary_objects)
    return (*objects, *(mesh.data.shape_keys for mesh in meshes if mesh.data.shape_keys))


@contextmanager
def sample_state(meshes, armature, auxiliary_objects=()):
    ids = animated_ids(meshes, armature, auxiliary_objects)
    saved = [(item, item.animation_data.action, item.animation_data.use_nla,
              getattr(item.animation_data, "action_slot", None))
             for item in ids if item.animation_data]
    shapes = [(key, key.value) for mesh in meshes if mesh.data.shape_keys
              for key in mesh.data.shape_keys.key_blocks]
    frame = bpy.context.scene.frame_current
    subframe = bpy.context.scene.frame_subframe
    pose = armature.data.pose_position if armature else None
    bone_transforms = [(bone, bone.matrix_basis.copy()) for bone in armature.pose.bones] if armature else ()
    try:
        yield ids
    finally:
        for item, action, use_nla, slot in saved:
            item.animation_data.action = action
            if slot is not None:
                item.animation_data.action_slot = slot
            item.animation_data.use_nla = use_nla
        if armature:
            armature.data.pose_position = pose
        bpy.context.scene.frame_set(frame, subframe=subframe)
        for key, value in shapes:
            key.value = value
        for bone, matrix in bone_transforms:
            bone.matrix_basis = matrix
        bpy.context.view_layer.update()


def bind_clip(ids, name, *, armature=None, actions=None):
    """Match track labels, not globally renamed Action datablocks or slots."""
    for item in ids:
        animation = item.animation_data
        if animation is None:
            continue
        current_action = animation.action
        current_slot = getattr(animation, "action_slot", None)
        binding = None
        for track in animation.nla_tracks:
            for strip in track.strips:
                if strip.action and (track.name == name or strip.action.name == name):
                    binding = (strip.action, getattr(strip, "action_slot", None))
                    break
            if binding:
                break
        if binding is None and current_action and current_action.name == name:
            binding = (current_action, current_slot)
        if binding is None and item is armature and actions and name in actions:
            binding = (actions[name], None)
        animation.use_nla = False
        animation.action = binding[0] if binding else None
        if binding and binding[1] is not None:
            animation.action_slot = binding[1]


def world_points(meshes):
    points = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for mesh in meshes:
        evaluated = mesh.evaluated_get(depsgraph)
        data = evaluated.to_mesh()
        try:
            points.extend(tuple(evaluated.matrix_world @ vertex.co) for vertex in data.vertices)
        finally:
            evaluated.to_mesh_clear()
    return tuple(points)


def skin_records(meshes, armature):
    bones = set(armature.data.bones.keys()) if armature else set()
    records = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for mesh in meshes:
        groups = {group.index: group.name for group in mesh.vertex_groups if group.name in bones}
        evaluated = mesh.evaluated_get(depsgraph)
        data = evaluated.to_mesh()
        try:
            if len(data.vertices) != len(mesh.data.vertices):
                raise ValueError("Round-trip skin checks do not support topology-changing modifiers.")
            for vertex in mesh.data.vertices:
                weights = {groups[group.group]: float(group.weight) for group in vertex.groups
                           if group.group in groups and group.weight > 1.0e-7}
                # Blender deformation and glTF both use normalized influences.
                # The imported source may store equivalent unnormalized values.
                total = sum(weights.values())
                if total:
                    weights = {name: weight / total for name, weight in weights.items()}
                position = evaluated.matrix_world @ data.vertices[vertex.index].co
                records.append((tuple(position), weights))
        finally:
            evaluated.to_mesh_clear()
    return tuple(records)


def material_signatures(meshes):
    signatures = set()
    for mesh in meshes:
        for material in mesh.data.materials:
            if material is None:
                continue
            principled = next((node for node in material.node_tree.nodes
                               if node.type == "BSDF_PRINCIPLED"), None) if material.node_tree else None
            values = []
            if principled:
                for name in ("Base Color", "Metallic", "Roughness", "Alpha"):
                    value = principled.inputs[name].default_value
                    values.append(tuple(round(float(v), 4) for v in value)
                                  if hasattr(value, "__len__") else round(float(value), 4))
            textures = []
            if material.node_tree:
                for node in material.node_tree.nodes:
                    if node.type == "TEX_IMAGE" and node.image:
                        pixels = node.image.pixels
                        stride = max(1, len(pixels) // 32)
                        textures.append((tuple(node.image.size),
                                         tuple(round(float(pixels[i]), 3)
                                               for i in range(0, len(pixels), stride))))
            signatures.add((tuple(values), tuple(sorted(textures))))
    return signatures


def observe(meshes, armature, clips, *, actions=None, auxiliary_objects=()):
    with sample_state(meshes, armature, auxiliary_objects) as ids:
        # Global transforms may be animated too. Anchor the rest observation
        # at a deterministic clip origin, not the user's current root position.
        if clips:
            if armature:
                armature.data.pose_position = "POSE"
            bind_clip(ids, clips[0][0], armature=armature, actions=actions)
            bpy.context.scene.frame_set(math.floor(clips[0][1]))
            bpy.context.view_layer.update()
        else:
            bpy.context.scene.frame_set(0)
            bpy.context.view_layer.update()
        for item in ids:
            if item.animation_data:
                item.animation_data.action = None
                item.animation_data.use_nla = False
        for mesh in meshes:
            if mesh.data.shape_keys:
                for key in mesh.data.shape_keys.key_blocks:
                    key.value = 0.0
        if armature:
            armature.data.pose_position = "REST"
        bpy.context.view_layer.update()
        rest = world_points(meshes)
        weights = skin_records(meshes, armature)
        hierarchy = {bone.name: bone.parent.name if bone.parent else None
                     for bone in armature.data.bones} if armature else {}
        morph_count = sum(len(mesh.data.shape_keys.key_blocks) - 1 for mesh in meshes
                          if mesh.data.shape_keys)
        samples = {}
        if armature:
            armature.data.pose_position = "POSE"
        for name, start, end in clips:
            # Clips are independent. Missing channels must not inherit the end
            # pose of the preceding clip (e.g. Death -> Idle).
            for item in ids:
                if item.animation_data:
                    item.animation_data.action = None
                    item.animation_data.use_nla = False
            bpy.context.view_layer.update()
            if armature:
                for bone in armature.pose.bones:
                    bone.matrix_basis = Matrix.Identity(4)
            for mesh in meshes:
                if mesh.data.shape_keys:
                    for key in mesh.data.shape_keys.key_blocks:
                        key.value = 0.0
            bind_clip(ids, name, armature=armature, actions=actions)
            for index in range(5):
                # Blender's sampled glTF export uses integer frame bounds.
                # Compare identical sample instants, not different normalized
                # times when a fractional last key is quantized by the exporter.
                frame = math.floor(start) + round((math.floor(end) - math.floor(start)) * index / 4)
                integer = int(frame)
                bpy.context.scene.frame_set(integer, subframe=frame - integer)
                bpy.context.view_layer.update()
                samples[(name, index)] = world_points(meshes)
        return {
            "rest": rest, "skin": weights, "hierarchy": hierarchy,
            "morph_count": morph_count, "materials": material_signatures(meshes),
            "samples": samples,
        }
