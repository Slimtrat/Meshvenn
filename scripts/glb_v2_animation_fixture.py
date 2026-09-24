"""Blender helpers for the animated character V2 roundtrip fixture."""

from __future__ import annotations

import math
from pathlib import Path

import bpy

from scripts.benchmark_rig_v2 import (
    EXPECTED_BONES,
    _evaluated_positions,
    _skin_rows,
)
from scripts.glb_v2_character_support import assert_unrigged_mesh
from scripts.glb_v2_rig_metrics import skin_weight_summary
from scripts.render_turntable import clear_scene


def inspect_isolated_reference(path: Path) -> dict:
    """Prove that the intermediate rendered GLB contains no source rig data."""
    clear_scene()
    actions_before = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    new_actions = set(bpy.data.actions) - actions_before
    if len(meshes) != 1 or armatures or new_actions:
        raise AssertionError("Isolated reference GLB retained source rig or animation data")
    assert_unrigged_mesh(meshes[0])
    return {
        "mesh_count": len(meshes),
        "armature_count": len(armatures),
        "animation_count": len(new_actions),
        "vertex_group_count": len(meshes[0].vertex_groups),
    }


def author_validation_action(armature: bpy.types.Object) -> str:
    """Create a deterministic three-key pose clip on the generated rig."""
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 24
    scene.render.fps = 24
    armature.animation_data_create()
    action = bpy.data.actions.new("MeshVenn_Character_E2E")
    armature.animation_data.action = action
    bone = armature.pose.bones["upper_arm.L"]
    bone.rotation_mode = "XYZ"
    for frame, angle in ((1, 0.0), (12, 35.0), (24, 0.0)):
        scene.frame_set(frame)
        bone.rotation_euler[1] = math.radians(angle)
        bone.keyframe_insert(data_path="rotation_euler", frame=frame, group=bone.name)
    scene.frame_set(1)
    bpy.context.view_layer.update()
    return action.name


def animated_glb_roundtrip(
    mesh: bpy.types.Object,
    armature: bpy.types.Object,
    path: Path,
) -> dict:
    """Export and reimport skin plus animation, then measure the imported pose."""
    action_name = author_validation_action(armature)
    for selected in tuple(bpy.context.selected_objects):
        selected.select_set(False)
    mesh.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    result = bpy.ops.export_scene.gltf(
        filepath=str(path.resolve()),
        export_format="GLB",
        use_selection=True,
        export_animations=True,
    )
    if "FINISHED" not in result or not path.is_file():
        raise AssertionError("Animated character GLB export failed")

    objects_before = {obj.as_pointer() for obj in bpy.data.objects}
    actions_before = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    imported = [obj for obj in bpy.data.objects if obj.as_pointer() not in objects_before]
    new_actions = set(bpy.data.actions) - actions_before
    arms = [obj for obj in imported if obj.type == "ARMATURE"]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if len(arms) != 1 or not meshes or set(arms[0].data.bones.keys()) != EXPECTED_BONES:
        raise AssertionError("Animated GLB roundtrip lost canonical bones or mesh")
    bound = [obj for obj in meshes if any(
        modifier.type == "ARMATURE" and modifier.object is arms[0]
        for modifier in obj.modifiers
    )]
    if len(bound) != 1:
        raise AssertionError("Animated GLB roundtrip lost skin binding")
    if not new_actions or arms[0].animation_data is None or arms[0].animation_data.action is None:
        raise AssertionError("Animated GLB roundtrip lost the validation action")

    scene = bpy.context.scene
    scene.frame_set(1)
    rest = _evaluated_positions(bound[0])
    scene.frame_set(12)
    posed = _evaluated_positions(bound[0])
    if len(rest) != len(posed):
        raise AssertionError("Imported animation changed mesh topology")
    left = [math.dist(a, b) for a, b in zip(rest, posed) if a[0] > 0.10]
    right = [math.dist(a, b) for a, b in zip(rest, posed) if a[0] < -0.10]
    if not left or not right:
        raise AssertionError("Imported character lacks bilateral animation samples")
    scene.frame_set(1)
    weights = skin_weight_summary(_skin_rows(bound[0], arms[0]))
    return {
        "glb_bytes": path.stat().st_size,
        "bone_count": len(arms[0].data.bones),
        "animation_count": len(new_actions),
        "source_action_name": action_name,
        "imported_action_names": sorted(action.name for action in new_actions),
        "frame_start": 1,
        "frame_peak": 12,
        "frame_end": 24,
        "left_mean_displacement": sum(left) / len(left),
        "right_mean_displacement": sum(right) / len(right),
        "left_max_displacement": max(left),
        "right_max_displacement": max(right),
        **weights,
    }
