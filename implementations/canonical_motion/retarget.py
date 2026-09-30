"""Rest/global-space animation retargeting onto a Canonical Biped armature."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import bpy

from .mapping import ResolvedBoneMap


ROOT_MOTION_MODE = "IN_PLACE"


@dataclass(frozen=True)
class TargetAnimationSnapshot:
    had_animation_data: bool
    action: Any
    use_nla: bool
    bone_states: tuple[tuple[str, str, Any], ...]


@dataclass(frozen=True)
class BakedAction:
    name: str
    action: Any
    frame_start: int
    frame_end: int
    fps: float
    animated_roles: tuple[str, ...]
    pose_samples: int


def snapshot_target_animation(armature: Any, bone_names: tuple[str, ...]) -> TargetAnimationSnapshot:
    animation_data = armature.animation_data
    states = tuple(
        (name, armature.pose.bones[name].rotation_mode, armature.pose.bones[name].matrix_basis.copy())
        for name in bone_names
    )
    return TargetAnimationSnapshot(
        had_animation_data=animation_data is not None,
        action=animation_data.action if animation_data is not None else None,
        use_nla=animation_data.use_nla if animation_data is not None else True,
        bone_states=states,
    )


def restore_target_animation(armature: Any, snapshot: TargetAnimationSnapshot) -> None:
    for name, rotation_mode, matrix_basis in snapshot.bone_states:
        pose_bone = armature.pose.bones.get(name)
        if pose_bone is not None:
            pose_bone.rotation_mode = rotation_mode
            pose_bone.matrix_basis = matrix_basis
    if snapshot.had_animation_data:
        animation_data = armature.animation_data_create()
        animation_data.action = snapshot.action
        animation_data.use_nla = snapshot.use_nla
    elif armature.animation_data is not None:
        armature.animation_data_clear()


def _reset_target_pose(target_armature: Any, bone_map: ResolvedBoneMap, root_bone: str) -> None:
    target_armature.pose.bones[root_bone].matrix_basis.identity()
    for entry in bone_map.entries:
        pose_bone = target_armature.pose.bones[entry.target_bone]
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.location = (0.0, 0.0, 0.0)
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.scale = (1.0, 1.0, 1.0)


def _base_pose_matrix(target_armature: Any, target_name: str) -> Any:
    pose_bone = target_armature.pose.bones[target_name]
    rest_bone = target_armature.data.bones[target_name]
    if pose_bone.parent is None:
        return rest_bone.matrix_local.copy()
    return (
        pose_bone.parent.matrix
        @ pose_bone.parent.bone.matrix_local.inverted_safe()
        @ rest_bone.matrix_local
    )


def _retarget_rotation(
    source_armature: Any,
    target_armature: Any,
    source_name: str,
    target_name: str,
) -> Any:
    source_rest_world = source_armature.matrix_world @ source_armature.data.bones[source_name].matrix_local
    source_pose_world = source_armature.matrix_world @ source_armature.pose.bones[source_name].matrix
    source_delta = source_pose_world.to_quaternion() @ source_rest_world.to_quaternion().inverted()

    target_rest_world = target_armature.matrix_world @ target_armature.data.bones[target_name].matrix_local
    desired_world = source_delta @ target_rest_world.to_quaternion()
    base_world = (target_armature.matrix_world @ _base_pose_matrix(target_armature, target_name)).to_quaternion()
    result = base_world.inverted() @ desired_world
    result.normalize()
    return result


def _make_quaternion_continuous(current: Any, previous: Any | None) -> Any:
    value = current.copy()
    if previous is not None and value.dot(previous) < 0.0:
        value.negate()
    return value


def _set_linear_interpolation(action: Any) -> None:
    try:
        curves = tuple(action.fcurves)
    except (AttributeError, RuntimeError, TypeError):
        return
    for curve in curves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"


def bake_retargeted_action(
    source_armature: Any,
    target_armature: Any,
    source_action: Any,
    bone_map: ResolvedBoneMap,
    *,
    root_bone: str,
    fps: float,
    action_name: str,
    root_motion_mode: str = ROOT_MOTION_MODE,
) -> BakedAction:
    if root_motion_mode != ROOT_MOTION_MODE:
        raise ValueError(f"Unsupported root motion mode: {root_motion_mode}")
    start_value, end_value = (float(value) for value in source_action.frame_range)
    frame_start = math.floor(min(start_value, end_value))
    frame_end = math.ceil(max(start_value, end_value))
    if frame_end <= frame_start:
        raise ValueError(f'Motion action "{source_action.name}" has no animated frame range')

    source_animation = source_armature.animation_data_create()
    source_animation.use_nla = False
    source_animation.action = source_action
    target_animation = target_armature.animation_data_create()
    target_animation.use_nla = False
    target_action = bpy.data.actions.new(name=action_name)
    target_action.use_fake_user = True
    target_animation.action = target_action

    previous_quaternions: dict[str, Any] = {}
    pose_samples = 0
    for frame in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(frame)
        _reset_target_pose(target_armature, bone_map, root_bone)
        bpy.context.view_layer.update()
        for entry in bone_map.entries:
            pose_bone = target_armature.pose.bones[entry.target_bone]
            rotation = _retarget_rotation(
                source_armature,
                target_armature,
                entry.source_bone,
                entry.target_bone,
            )
            rotation = _make_quaternion_continuous(
                rotation,
                previous_quaternions.get(entry.target_bone),
            )
            pose_bone.rotation_quaternion = rotation
            pose_bone.keyframe_insert(
                data_path="rotation_quaternion",
                frame=frame,
                group=entry.target_bone,
            )
            previous_quaternions[entry.target_bone] = rotation.copy()
            pose_samples += 1
        bpy.context.view_layer.update()
    _set_linear_interpolation(target_action)
    return BakedAction(
        name=source_action.name,
        action=target_action,
        frame_start=frame_start,
        frame_end=frame_end,
        fps=float(fps),
        animated_roles=bone_map.animated_roles,
        pose_samples=pose_samples,
    )


__all__ = (
    "ROOT_MOTION_MODE",
    "BakedAction",
    "TargetAnimationSnapshot",
    "bake_retargeted_action",
    "restore_target_animation",
    "snapshot_target_animation",
)
