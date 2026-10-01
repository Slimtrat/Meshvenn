"""Transactional Blender import and neutral-mesh normalization for GLB-first."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import bpy

from ...core.geometry_contracts import GeometryProjectionSpace
from ..canonical_motion.mapping import detect_source_profile
from ..canonical_motion.source import BlenderDataSnapshot, snapshot_blender_data


@dataclass(frozen=True)
class SourceRigEvidence:
    armature_count: int
    action_count: int
    supported_profile: str | None
    profile_certification: str | None

    @property
    def motion_compatible(self) -> bool:
        return self.supported_profile is not None and self.action_count > 0


@dataclass(frozen=True)
class NormalizedGLBGeometry:
    mesh_object: Any
    source_mesh_count: int
    source_vertex_count: int
    source_polygon_count: int
    source_rig: SourceRigEvidence
    original_dimensions: tuple[float, float, float]
    normalized_dimensions: tuple[float, float, float]
    normalization_scale: float
    projection_space: GeometryProjectionSpace


@dataclass(frozen=True)
class _UIState:
    active_object: Any | None
    active_mode: str
    selected_objects: tuple[Any, ...]
    frame_current: int


def _capture_ui_state() -> _UIState:
    active = bpy.context.view_layer.objects.active
    return _UIState(
        active_object=active,
        active_mode=active.mode if active is not None else "OBJECT",
        selected_objects=tuple(bpy.context.selected_objects),
        frame_current=bpy.context.scene.frame_current,
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
            try:
                obj.select_set(True)
            except RuntimeError:
                pass
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
) -> None:
    preserved = set(preserve_objects)
    for obj in tuple(bpy.data.objects):
        if obj not in snapshot.objects and obj not in preserved:
            bpy.data.objects.remove(obj, do_unlink=True)
    for action in tuple(bpy.data.actions):
        if action not in snapshot.actions:
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


def _rig_evidence(imported_objects: tuple[Any, ...], snapshot: BlenderDataSnapshot) -> SourceRigEvidence:
    armatures = tuple(obj for obj in imported_objects if obj.type == "ARMATURE")
    supported = []
    for armature in armatures:
        try:
            profile = detect_source_profile(bone.name for bone in armature.data.bones)
        except ValueError:
            continue
        supported.append(profile)
    profile = supported[0] if len(armatures) == 1 and len(supported) == 1 else None
    return SourceRigEvidence(
        armature_count=len(armatures),
        action_count=len(set(bpy.data.actions) - set(snapshot.actions)),
        supported_profile=profile.identifier if profile is not None else None,
        profile_certification=profile.certification if profile is not None else None,
    )


def _duplicate_neutral_mesh(source: Any) -> Any:
    duplicate = source.copy()
    duplicate.data = source.data.copy()
    bpy.context.scene.collection.objects.link(duplicate)
    world = source.matrix_world.copy()
    duplicate.parent = None
    duplicate.matrix_world = world
    duplicate.animation_data_clear()
    for modifier in tuple(duplicate.modifiers):
        if modifier.type == "ARMATURE":
            duplicate.modifiers.remove(modifier)
    for group in tuple(duplicate.vertex_groups):
        duplicate.vertex_groups.remove(group)
    if duplicate.data.shape_keys is not None:
        duplicate.shape_key_clear()
    duplicate.hide_set(False)
    duplicate.hide_viewport = False
    duplicate.hide_render = False
    duplicate.hide_select = False
    return duplicate


def _join_meshes(mesh_objects: tuple[Any, ...]) -> Any:
    for selected in tuple(bpy.context.selected_objects):
        selected.select_set(False)
    for obj in mesh_objects:
        obj.select_set(True)
    active = mesh_objects[0]
    bpy.context.view_layer.objects.active = active
    bpy.context.view_layer.update()
    applied = bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if "FINISHED" not in applied:
        raise RuntimeError(f"Could not apply imported GLB transforms: {applied}")
    if len(mesh_objects) > 1:
        joined = bpy.ops.object.join()
        if "FINISHED" not in joined:
            raise RuntimeError(f"Could not join imported GLB meshes: {joined}")
    active.name = "Meshvenn_GLB_Geometry"
    active.data.name = "Meshvenn_GLB_Geometry_Mesh"
    for group in tuple(active.vertex_groups):
        active.vertex_groups.remove(group)
    for modifier in tuple(active.modifiers):
        if modifier.type == "ARMATURE":
            active.modifiers.remove(modifier)
    return active


def _bounds(mesh: Any) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    coordinates = tuple(vertex.co for vertex in mesh.data.vertices)
    if not coordinates:
        raise ValueError("Imported GLB geometry contains no vertices.")
    minimum = tuple(min(co[index] for co in coordinates) for index in range(3))
    maximum = tuple(max(co[index] for co in coordinates) for index in range(3))
    return minimum, maximum


def _normalize_mesh(mesh: Any, target_extent: float) -> tuple[
    tuple[float, float, float], tuple[float, float, float], float, GeometryProjectionSpace
]:
    minimum, maximum = _bounds(mesh)
    original_dimensions = tuple(maximum[i] - minimum[i] for i in range(3))
    longest = max(original_dimensions)
    if not math.isfinite(longest) or longest <= 1.0e-8:
        raise ValueError("Imported GLB geometry has a zero-size bounding box.")
    scale = target_extent / longest
    center_x = (minimum[0] + maximum[0]) * 0.5
    center_y = (minimum[1] + maximum[1]) * 0.5
    base_z = minimum[2]
    for vertex in mesh.data.vertices:
        vertex.co.x = (vertex.co.x - center_x) * scale
        vertex.co.y = (vertex.co.y - center_y) * scale
        vertex.co.z = (vertex.co.z - base_z) * scale
    mesh.data.validate(verbose=True)
    mesh.data.update()
    normalized_dimensions = tuple(value * scale for value in original_dimensions)
    voxel_size = target_extent / 256.0
    dimensions = tuple(max(1, math.ceil(value / voxel_size)) for value in normalized_dimensions)
    projection_space = GeometryProjectionSpace(
        width=dimensions[0],
        depth=dimensions[1],
        height=dimensions[2],
        voxel_size=voxel_size,
        center_xy=True,
    )
    return original_dimensions, normalized_dimensions, scale, projection_space


def import_and_normalize_glb(path: str, *, target_extent: float) -> NormalizedGLBGeometry:
    if not math.isfinite(target_extent) or target_extent <= 0.0:
        raise ValueError("GLB normalized extent must be finite and greater than zero.")
    snapshot = snapshot_blender_data()
    ui_state = _capture_ui_state()
    normalized = None
    try:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        result = bpy.ops.import_scene.gltf(filepath=path)
        if "FINISHED" not in result:
            raise RuntimeError(f"Blender GLB import failed: {result}")
        imported_objects = tuple(obj for obj in bpy.data.objects if obj not in snapshot.objects)
        source_meshes = tuple(obj for obj in imported_objects if obj.type == "MESH")
        if not source_meshes:
            raise ValueError("Imported GLB contains no Blender mesh object.")
        evidence = _rig_evidence(imported_objects, snapshot)
        source_vertex_count = sum(len(obj.data.vertices) for obj in source_meshes)
        source_polygon_count = sum(len(obj.data.polygons) for obj in source_meshes)
        neutral_meshes = tuple(_duplicate_neutral_mesh(obj) for obj in source_meshes)
        normalized = _join_meshes(neutral_meshes)
        original, dimensions, scale, projection_space = _normalize_mesh(
            normalized, target_extent
        )
        _cleanup_new_data(snapshot, preserve_objects=(normalized,))
        return NormalizedGLBGeometry(
            mesh_object=normalized,
            source_mesh_count=len(source_meshes),
            source_vertex_count=source_vertex_count,
            source_polygon_count=source_polygon_count,
            source_rig=evidence,
            original_dimensions=original,
            normalized_dimensions=dimensions,
            normalization_scale=scale,
            projection_space=projection_space,
        )
    except Exception:
        _cleanup_new_data(snapshot)
        raise
    finally:
        _restore_ui_state(ui_state)


__all__ = (
    "NormalizedGLBGeometry",
    "SourceRigEvidence",
    "import_and_normalize_glb",
)
