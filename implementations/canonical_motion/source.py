"""Transactional import and cleanup of external GLB motion sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpy

from .mapping import MotionSourceProfile, detect_source_profile


@dataclass(frozen=True)
class BlenderDataSnapshot:
    objects: frozenset[Any]
    actions: frozenset[Any]
    armatures: frozenset[Any]
    meshes: frozenset[Any]
    materials: frozenset[Any]
    images: frozenset[Any]
    collections: frozenset[Any]


@dataclass(frozen=True)
class ImportedMotionSource:
    path: Path
    armature: Any
    profile: MotionSourceProfile
    actions: tuple[Any, ...]
    imported_objects: tuple[Any, ...]


def snapshot_blender_data() -> BlenderDataSnapshot:
    return BlenderDataSnapshot(
        objects=frozenset(bpy.data.objects),
        actions=frozenset(bpy.data.actions),
        armatures=frozenset(bpy.data.armatures),
        meshes=frozenset(bpy.data.meshes),
        materials=frozenset(bpy.data.materials),
        images=frozenset(bpy.data.images),
        collections=frozenset(bpy.data.collections),
    )


def _action_data_paths(action: Any) -> tuple[str, ...]:
    try:
        return tuple(curve.data_path for curve in action.fcurves)
    except (AttributeError, RuntimeError, TypeError):
        return ()


def _motion_actions(armature: Any, new_actions: set[Any]) -> tuple[Any, ...]:
    linked = []
    animation_data = armature.animation_data
    if animation_data is not None:
        if animation_data.action is not None:
            linked.append(animation_data.action)
        for track in animation_data.nla_tracks:
            linked.extend(strip.action for strip in track.strips if strip.action is not None)

    required_path_tokens = tuple(f'pose.bones["{bone.name}"]' for bone in armature.data.bones)
    bone_actions = [
        action for action in new_actions
        if any(token in path for path in _action_data_paths(action) for token in required_path_tokens)
    ]
    candidates = []
    for action in (*linked, *bone_actions):
        if action in new_actions and action not in candidates:
            candidates.append(action)
    if not candidates and len(new_actions) == 1:
        candidates = list(new_actions)
    candidates.sort(key=lambda action: action.name)
    return tuple(candidates)


def import_external_motion(path: Path, snapshot: BlenderDataSnapshot) -> ImportedMotionSource:
    source_path = Path(path).expanduser().resolve()
    if source_path.suffix.lower() != ".glb":
        raise ValueError("Canonical motion requires an external .glb source")
    if not source_path.is_file():
        raise FileNotFoundError(f"Motion source GLB does not exist: {source_path}")

    result = bpy.ops.import_scene.gltf(filepath=str(source_path))
    if "FINISHED" not in result:
        raise RuntimeError(f"Blender GLB import failed: {result}")
    imported_objects = tuple(obj for obj in bpy.data.objects if obj not in snapshot.objects)
    new_actions = set(bpy.data.actions) - set(snapshot.actions)
    armatures = []
    for obj in imported_objects:
        if obj.type != "ARMATURE":
            continue
        try:
            profile = detect_source_profile(bone.name for bone in obj.data.bones)
        except ValueError:
            continue
        armatures.append((obj, profile))
    if len(armatures) != 1:
        raise ValueError(
            "Motion GLB must contain exactly one supported RiggedFigure armature; "
            f"found {len(armatures)}"
        )
    armature, profile = armatures[0]
    actions = _motion_actions(armature, new_actions)
    if not actions:
        raise ValueError("Motion GLB contains no animation action for its supported armature")
    return ImportedMotionSource(source_path, armature, profile, actions, imported_objects)


def cleanup_imported_data(
    snapshot: BlenderDataSnapshot,
    *,
    preserve_actions: tuple[Any, ...] = (),
) -> None:
    """Remove every datablock created since the source-import snapshot."""
    preserved = set(preserve_actions)
    for obj in tuple(bpy.data.objects):
        if obj not in snapshot.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for action in tuple(bpy.data.actions):
        if action not in snapshot.actions and action not in preserved:
            bpy.data.actions.remove(action)
    for collection, original in (
        (bpy.data.armatures, snapshot.armatures),
        (bpy.data.meshes, snapshot.meshes),
        (bpy.data.materials, snapshot.materials),
        (bpy.data.images, snapshot.images),
        (bpy.data.collections, snapshot.collections),
    ):
        for block in tuple(collection):
            if block not in original and block.users == 0:
                collection.remove(block)


__all__ = (
    "BlenderDataSnapshot",
    "ImportedMotionSource",
    "cleanup_imported_data",
    "import_external_motion",
    "snapshot_blender_data",
)
