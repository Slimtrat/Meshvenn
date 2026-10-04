"""Transactional GLB import that keeps source meshes, rig, skin and actions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Vector

from ...core.geometry_contracts import GeometryProjectionSpace
from ...core.rig_compatibility import (
    SOURCE_RIG_PRESERVATION_TARGET,
    RigCompatibilityReport,
    assess_rig_compatibility,
)
from ..canonical_motion.mapping import resolve_source_profile
from ..canonical_motion.source import (
    BlenderDataSnapshot,
    motion_actions_for_armature,
    snapshot_blender_data,
)
from ..glb_geometry.normalization import inspect_rig_structure


@dataclass(frozen=True)
class ImportedPreservedCharacter:
    mesh_objects: tuple[Any, ...]
    primary_mesh: Any
    armature_object: Any
    actions: tuple[Any, ...]
    source_profile_id: str
    source_profile_certification: str
    source_rig_archetype: str
    semantic_bones: dict[str, str]
    compatibility: RigCompatibilityReport
    source_vertex_count: int
    source_polygon_count: int
    original_dimensions: tuple[float, float, float]
    normalized_dimensions: tuple[float, float, float]
    normalization_scale: float
    projection_space: GeometryProjectionSpace
    auxiliary_objects: tuple[Any, ...]


@dataclass(frozen=True)
class _UIState:
    active_object: Any | None
    active_mode: str
    selected_objects: tuple[Any, ...]
    frame_current: int


def _capture_ui_state() -> _UIState:
    active = bpy.context.view_layer.objects.active
    return _UIState(
        active,
        active.mode if active is not None else "OBJECT",
        tuple(bpy.context.selected_objects),
        bpy.context.scene.frame_current,
    )


def _object_exists(obj: Any) -> bool:
    try:
        return bpy.data.objects.get(obj.name) is obj
    except ReferenceError:
        return False


def _restore_ui_state(state: _UIState) -> None:
    if bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    for obj in state.selected_objects:
        if _object_exists(obj):
            obj.select_set(True)
    if state.active_object is not None and _object_exists(state.active_object):
        bpy.context.view_layer.objects.active = state.active_object
        if state.active_mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode=state.active_mode)
            except RuntimeError:
                pass
    else:
        bpy.context.view_layer.objects.active = None
    bpy.context.scene.frame_set(state.frame_current)
    bpy.context.view_layer.update()


def _cleanup_new_data(
    snapshot: BlenderDataSnapshot,
    *,
    preserve_objects: tuple[Any, ...] = (),
    preserve_actions: tuple[Any, ...] = (),
) -> None:
    kept_objects = set(preserve_objects)
    kept_actions = set(preserve_actions)
    for obj in tuple(bpy.data.objects):
        if obj not in snapshot.objects and obj not in kept_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for action in tuple(bpy.data.actions):
        if action not in snapshot.actions and action not in kept_actions:
            bpy.data.actions.remove(action)
    for collection, original in (
        (bpy.data.armatures, snapshot.armatures),
        (bpy.data.meshes, snapshot.meshes),
        (bpy.data.materials, snapshot.materials),
        (bpy.data.images, snapshot.images),
        (bpy.data.collections, snapshot.collections),
        (bpy.data.cameras, snapshot.cameras),
        (bpy.data.lights, snapshot.lights),
    ):
        for block in tuple(collection):
            if block not in original and block.users == 0:
                collection.remove(block)


def _world_bounds(meshes: tuple[Any, ...]) -> tuple[Vector, Vector]:
    points = tuple(
        mesh.matrix_world @ Vector(corner)
        for mesh in meshes
        for corner in mesh.bound_box
    )
    if not points:
        raise ValueError("Preserved GLB character contains no mesh bounds.")
    minimum = Vector(tuple(min(point[index] for point in points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in points) for index in range(3)))
    return minimum, maximum


def _normalize_character(
    meshes: tuple[Any, ...], armature: Any, target_extent: float, source_roots: tuple[Any, ...]
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    float,
    GeometryProjectionSpace,
    Any,
]:
    minimum, maximum = _world_bounds(meshes)
    original = tuple(float(maximum[index] - minimum[index]) for index in range(3))
    longest = max(original)
    if not math.isfinite(longest) or longest <= 1.0e-8:
        raise ValueError("Preserved GLB character has a zero-size bounding box.")
    scale = target_extent / longest
    offset = Vector((
        -(minimum.x + maximum.x) * 0.5,
        -(minimum.y + maximum.y) * 0.5,
        -minimum.z,
    ))
    transform = Matrix.Scale(scale, 4) @ Matrix.Translation(offset)
    # Never put normalization into an animated object's transform: its action
    # would overwrite the scale/offset on the next frame evaluation.
    normalization_root = bpy.data.objects.new("Meshvenn_Normalization", None)
    bpy.context.scene.collection.objects.link(normalization_root)
    normalization_root.matrix_world = transform
    for root in source_roots:
        local = root.matrix_world.copy()
        root.parent = normalization_root
        root.matrix_parent_inverse = Matrix.Identity(4)
        root.matrix_basis = local
    bpy.context.view_layer.update()
    normalized = tuple(value * scale for value in original)
    voxel_size = target_extent / 256.0
    dimensions = tuple(max(1, math.ceil(value / voxel_size)) for value in normalized)
    return original, normalized, scale, GeometryProjectionSpace(
        width=dimensions[0],
        depth=dimensions[1],
        height=dimensions[2],
        voxel_size=voxel_size,
        center_xy=True,
    ), normalization_root


def _root_bone_name(armature: Any, pelvis_name: str) -> str:
    bone = armature.data.bones.get(pelvis_name)
    if bone is None:
        raise ValueError(f'Source pelvis bone does not exist: "{pelvis_name}"')
    while bone.parent is not None:
        bone = bone.parent
    return bone.name


def import_preserved_glb(
    path: str | Path, *, target_extent: float
) -> ImportedPreservedCharacter:
    if not math.isfinite(target_extent) or target_extent <= 0.0:
        raise ValueError("GLB preserved extent must be finite and greater than zero.")
    source_path = Path(path).expanduser().resolve(strict=True)
    snapshot = snapshot_blender_data()
    ui_state = _capture_ui_state()
    preserved_objects: tuple[Any, ...] = ()
    preserved_actions: tuple[Any, ...] = ()
    succeeded = False
    try:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        # The normalization reference must not depend on the user's timeline.
        bpy.context.scene.frame_set(0)
        result = bpy.ops.import_scene.gltf(filepath=str(source_path), bone_heuristic="TEMPERANCE")
        if "FINISHED" not in result:
            raise RuntimeError(f"Blender GLB import failed: {result}")
        imported = tuple(obj for obj in bpy.data.objects if obj not in snapshot.objects)
        armatures = tuple(obj for obj in imported if obj.type == "ARMATURE")
        custom_shapes = {bone.custom_shape for rig in armatures for bone in rig.pose.bones
                         if bone.custom_shape is not None}
        meshes = tuple(obj for obj in imported if obj.type == "MESH" and obj not in custom_shapes)
        if not meshes:
            raise ValueError("Source-preservation GLB contains no mesh.")
        if len(armatures) != 1:
            raise ValueError(
                "Source-preservation GLB requires exactly one armature; "
                f"found {len(armatures)}."
            )
        armature = armatures[0]
        resolved = resolve_source_profile(bone.name for bone in armature.data.bones)
        structure = inspect_rig_structure(imported, armatures)
        compatibility = assess_rig_compatibility(
            structure,
            source_profile=resolved.profile.identifier,
            declared_archetype=resolved.profile.rig_archetype,
            compatible_targets=resolved.profile.compatible_target_rigs,
            target_rig=SOURCE_RIG_PRESERVATION_TARGET,
        )
        if not compatibility.routable:
            raise ValueError("Source rig is not eligible for preservation routing.")
        actions = motion_actions_for_armature(
            armature, set(bpy.data.actions) - set(snapshot.actions)
        )
        semantics = {
            "root": _root_bone_name(armature, resolved.role_to_bone["pelvis"]),
            **resolved.role_to_bone,
        }
        source_vertex_count = sum(len(mesh.data.vertices) for mesh in meshes)
        source_polygon_count = sum(len(mesh.data.polygons) for mesh in meshes)
        ancestors = set()
        for obj in (*meshes, armature):
            parent = obj.parent
            while parent is not None:
                if parent not in imported or parent.type != "EMPTY":
                    if parent is armature:
                        parent = parent.parent
                        continue
                    raise ValueError("Preservation requires supported source hierarchy parents.")
                ancestors.add(parent)
                parent = parent.parent
        preserved = (*meshes, armature, *sorted(ancestors, key=lambda obj: obj.name))
        roots = tuple(obj for obj in preserved if obj.parent is None)
        unexpected_actions = set(bpy.data.actions) - set(snapshot.actions) - set(actions)
        if unexpected_actions:
            raise ValueError("Source contains clips without a supported armature action; preservation refused.")
        original, normalized, scale, projection_space, normalization_root = _normalize_character(
            meshes, armature, target_extent, roots
        )
        primary = max(meshes, key=lambda mesh: len(mesh.data.vertices))
        preserved_objects = (*preserved, normalization_root)
        preserved_actions = actions
        _cleanup_new_data(
            snapshot,
            preserve_objects=preserved_objects,
            preserve_actions=preserved_actions,
        )
        succeeded = True
        return ImportedPreservedCharacter(
            mesh_objects=meshes,
            primary_mesh=primary,
            armature_object=armature,
            actions=actions,
            source_profile_id=resolved.profile.identifier,
            source_profile_certification=resolved.profile.certification,
            source_rig_archetype=resolved.profile.rig_archetype,
            semantic_bones=semantics,
            compatibility=compatibility,
            source_vertex_count=source_vertex_count,
            source_polygon_count=source_polygon_count,
            original_dimensions=original,
            normalized_dimensions=normalized,
            normalization_scale=scale,
            projection_space=projection_space,
            auxiliary_objects=(*sorted(ancestors, key=lambda obj: obj.name), normalization_root),
        )
    finally:
        if not succeeded:
            _cleanup_new_data(snapshot)
        _restore_ui_state(ui_state)


__all__ = ("ImportedPreservedCharacter", "import_preserved_glb")
