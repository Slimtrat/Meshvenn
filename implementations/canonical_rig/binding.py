"""Blender armature creation and exportable mesh skinning."""

from __future__ import annotations

import math
import bpy

from ...core.canonical_rig import BoneSpec, fallback_weights


def _selection_snapshot():
    view_layer = bpy.context.view_layer
    return view_layer.objects.active, tuple(bpy.context.selected_objects)


def _restore_selection(active, selected) -> None:
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    for obj in selected:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    if active is not None and active.name in bpy.data.objects:
        bpy.context.view_layer.objects.active = active
    else:
        bpy.context.view_layer.objects.active = None


def create_armature(mesh_object: bpy.types.Object, bones: tuple[BoneSpec, ...]) -> bpy.types.Object:
    data = bpy.data.armatures.new("MeshvennCanonicalRig")
    armature = bpy.data.objects.new("MeshvennCanonicalRig", data)
    collection = mesh_object.users_collection[0] if mesh_object.users_collection else bpy.context.scene.collection
    collection.objects.link(armature)
    armature.matrix_world = mesh_object.matrix_world.copy()
    active, selected = _selection_snapshot()
    try:
        for obj in selected:
            obj.select_set(False)
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.mode_set(mode="EDIT")
        for spec in bones:
            edit_bone = data.edit_bones.new(spec.name)
            edit_bone.head = spec.head
            edit_bone.tail = spec.tail
            edit_bone.use_deform = spec.deform
            if spec.parent is not None:
                edit_bone.parent = data.edit_bones[spec.parent]
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        if armature.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.data.objects.remove(armature, do_unlink=True)
        if data.users == 0:
            bpy.data.armatures.remove(data)
        raise
    finally:
        _restore_selection(active, selected)
    return armature


def _remove_new_binding(mesh_object, original_groups, original_modifiers, original_parent, original_world) -> None:
    for modifier in tuple(mesh_object.modifiers):
        if modifier.name not in original_modifiers:
            mesh_object.modifiers.remove(modifier)
    for group in tuple(mesh_object.vertex_groups):
        if group.name not in original_groups:
            mesh_object.vertex_groups.remove(group)
    mesh_object.parent = original_parent
    mesh_object.matrix_world = original_world


def _normalize_skin_weights(mesh_object, bones: tuple[BoneSpec, ...]) -> None:
    by_name = {
        group.name: group for group in mesh_object.vertex_groups
        if any(spec.deform and spec.name == group.name for spec in bones)
    }
    by_index = {group.index: group for group in by_name.values()}
    for vertex in mesh_object.data.vertices:
        memberships = tuple(member for member in vertex.groups if member.group in by_index)
        valid = sorted(
            (
                (float(member.weight), member.group)
                for member in memberships
                if math.isfinite(member.weight) and member.weight > 0.0
            ),
            reverse=True,
        )[:4]
        if not valid:
            raise RuntimeError(f"Vertex {vertex.index} has no usable skin weights.")
        total = sum(weight for weight, _ in valid)
        kept = {index for _, index in valid}
        for member in memberships:
            if member.group not in kept:
                by_index[member.group].remove((vertex.index,))
        if len(memberships) != len(valid) or abs(total - 1.0) > 1e-4:
            for weight, index in valid:
                by_index[index].add((vertex.index,), weight / total, "REPLACE")


def _skin_coverage(mesh_object, bones: tuple[BoneSpec, ...]) -> tuple[int, int]:
    deform_names = {spec.name for spec in bones if spec.deform}
    deform_indices = {group.index for group in mesh_object.vertex_groups if group.name in deform_names}
    if len(deform_indices) != len(deform_names):
        return 0, len(mesh_object.data.vertices)
    invalid = 0
    max_influences = 0
    for vertex in mesh_object.data.vertices:
        weights = [
            float(member.weight) for member in vertex.groups
            if member.group in deform_indices and member.weight > 1e-8
        ]
        max_influences = max(max_influences, len(weights))
        if not weights or any(not math.isfinite(value) for value in weights) or abs(sum(weights) - 1.0) > 1e-3:
            invalid += 1
    return max_influences, invalid

def _bind_with_bone_heat(mesh_object, armature) -> None:
    active, selected = _selection_snapshot()
    try:
        for obj in selected:
            obj.select_set(False)
        mesh_object.select_set(True)
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        result = bpy.ops.object.parent_set(type="ARMATURE_AUTO", keep_transform=True)
        if "FINISHED" not in result:
            raise RuntimeError(f"Blender automatic weights returned {result}.")
    finally:
        _restore_selection(active, selected)


def _bind_with_distance_weights(mesh_object, armature, bones: tuple[BoneSpec, ...]) -> None:
    groups = {
        spec.name: mesh_object.vertex_groups.new(name=spec.name)
        for spec in bones if spec.deform
    }
    for vertex in mesh_object.data.vertices:
        for name, weight in fallback_weights(vertex.co, bones).items():
            groups[name].add((vertex.index,), weight, "REPLACE")
    modifier = mesh_object.modifiers.new("Meshvenn Skin", "ARMATURE")
    modifier.object = armature


def bind_mesh(mesh_object, armature, bones: tuple[BoneSpec, ...]) -> tuple[str, int]:
    """Prefer Blender bone heat; use deterministic weights on failure.

    Both paths create actual vertex groups and an Armature modifier, so the
    resulting asset remains exportable as a skinned GLB.
    """

    original_groups = {group.name for group in mesh_object.vertex_groups}
    original_modifiers = {modifier.name for modifier in mesh_object.modifiers}
    original_parent = mesh_object.parent
    original_world = mesh_object.matrix_world.copy()
    try:
        try:
            _bind_with_bone_heat(mesh_object, armature)
            _normalize_skin_weights(mesh_object, bones)
            max_influences, unweighted = _skin_coverage(mesh_object, bones)
            if unweighted:
                raise RuntimeError(f"Bone heat left {unweighted} vertices without skin weights.")
            return "blender-bone-heat", max_influences
        except Exception:
            _remove_new_binding(mesh_object, original_groups, original_modifiers, original_parent, original_world)
            _bind_with_distance_weights(mesh_object, armature, bones)
            _normalize_skin_weights(mesh_object, bones)
            max_influences, unweighted = _skin_coverage(mesh_object, bones)
            if unweighted:
                raise RuntimeError(f"Fallback left {unweighted} vertices without skin weights.")
            return "canonical-distance", max_influences
    except Exception:
        _remove_new_binding(mesh_object, original_groups, original_modifiers, original_parent, original_world)
        raise
