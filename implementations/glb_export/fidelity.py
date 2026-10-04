"""Fail-before-publish round-trip checks against the actual Blender output."""

from __future__ import annotations

import math

import bpy
from mathutils.kdtree import KDTree

from ..canonical_motion.source import cleanup_imported_data, snapshot_blender_data
from .fidelity_samples import observe


POSITION_TOLERANCE = 2.0e-4
WEIGHT_TOLERANCE = 1.0e-4


def _tree(points):
    if not points or any(not all(math.isfinite(value) for value in point) for point in points):
        raise ValueError("GLB round-trip contains empty or non-finite geometry.")
    tree = KDTree(len(points))
    for index, point in enumerate(points):
        tree.insert(point, index)
    tree.balance()
    return tree


def _surface_error(left, right):
    left_tree, right_tree = _tree(left), _tree(right)
    return max(max(right_tree.find(point)[2] for point in left),
               max(left_tree.find(point)[2] for point in right))


def _weight_error(left, right, tolerance):
    def directed(source, target):
        tree = _tree(tuple(point for point, _ in target))
        largest = 0.0
        for point, weights in source:
            candidates = tree.find_range(point, tolerance)
            if not candidates:
                raise ValueError("GLB round-trip lost a weighted vertex position.")
            error = min(max((abs(weights.get(name, 0.0) - target[index][1].get(name, 0.0))
                             for name in weights.keys() | target[index][1].keys()), default=0.0)
                        for _, index, _ in candidates)
            largest = max(largest, error)
        return largest
    return max(directed(left, right), directed(right, left))


def capture_expectation(plan):
    clips = tuple((clip.name, clip.frame_start, clip.frame_end)
                  for clip in plan.motion.clips) if plan.motion else ()
    return observe(plan.mesh_objects, plan.armature_object, clips,
                       actions={clip.name: clip.action for clip in plan.motion.clips} if plan.motion else None,
                       auxiliary_objects=plan.auxiliary_objects)


def validate_roundtrip(plan, path, *, sha256, expected):
    clips = tuple((clip.name, clip.frame_start, clip.frame_end)
                  for clip in plan.motion.clips) if plan.motion else ()
    extent = max(max(point[axis] for point in expected["rest"])
                 - min(point[axis] for point in expected["rest"]) for axis in range(3))
    tolerance = max(extent, 1.0e-6) * POSITION_TOLERANCE
    snapshot = snapshot_blender_data()
    try:
        result = bpy.ops.import_scene.gltf(filepath=str(path), bone_heuristic="TEMPERANCE")
        if "FINISHED" not in result:
            raise RuntimeError("GLB round-trip import failed.")
        imported = tuple(obj for obj in bpy.data.objects if obj not in snapshot.objects)
        armatures = tuple(obj for obj in imported if obj.type == "ARMATURE")
        custom_shapes = {bone.custom_shape for rig in armatures for bone in rig.pose.bones
                         if bone.custom_shape is not None}
        meshes = tuple(obj for obj in imported if obj.type == "MESH" and obj not in custom_shapes)
        if len(armatures) != int(plan.rig is not None):
            raise ValueError("GLB round-trip changed the armature count.")
        armature = armatures[0] if armatures else None
        imported_clips = []
        clip_labels = {}
        duration_error = 0.0
        if clips:
            tracks = {track.name: track for track in armature.animation_data.nla_tracks}
            fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
            for clip in plan.motion.clips:
                # Canonical clip labels may differ from baked Action names.
                track = tracks.get(clip.action.name) or tracks.get(clip.name)
                if track is None or len(track.strips) != 1 or track.strips[0].action is None:
                    raise ValueError(f"GLB round-trip lost animation {clip.name!r}.")
                action = track.strips[0].action
                start, end = action.frame_range
                error = abs((end - start) / fps - (clip.frame_end - clip.frame_start) / clip.fps)
                duration_error = max(duration_error, error)
                if error > 1.0 / fps + 1.0e-5:
                    raise ValueError(f"GLB round-trip changed clip duration: {clip.name!r}.")
                # Float32 GLB times can reimport just below an integer frame.
                # Compare the same original instants, not floor(imported_end)
                # which shifts probes by a whole frame. Duration is checked above.
                offset = 0.0
                if plan.motion.implementation_id == "glb-source-motion-v1":
                    # NLA exports use the strip clock (e.g. 1..31), while the
                    # source Action uses 0..30. Align origins, keeping the
                    # original sample spacing instead of rounding a new end.
                    offset = start - clip.frame_start
                    if abs(offset-round(offset)) <= 1e-4:
                        offset = round(offset)
                imported_clips.append((track.name, clip.frame_start+offset, clip.frame_end+offset))
                clip_labels[track.name] = clip.name
        actual = observe(meshes, armature, tuple(imported_clips),
                         auxiliary_objects=tuple(obj for obj in imported if obj.type == "EMPTY"))
        actual["samples"] = {(clip_labels[name], index): points
                             for (name, index), points in actual["samples"].items()}
        rest_error = _surface_error(expected["rest"], actual["rest"])
        pose_errors = {f"{name}:{index}": _surface_error(points, actual["samples"][(name, index)])
                       for (name, index), points in expected["samples"].items()}
        max_pose_error = max(pose_errors.values(), default=0.0)
        if rest_error > tolerance or max_pose_error > tolerance:
            raise ValueError(f"GLB round-trip geometry/deformation changed: rest={rest_error:.6g}, "
                             f"pose={max_pose_error:.6g}, tolerance={tolerance:.6g}; "
                             f"sample={max(pose_errors, key=pose_errors.get, default='rest')}.")
        if expected["hierarchy"] != actual["hierarchy"]:
            raise ValueError("GLB round-trip changed the bone hierarchy.")
        if expected["morph_count"] != actual["morph_count"]:
            raise ValueError("GLB round-trip lost morph targets.")
        if expected["materials"] != actual["materials"]:
            raise ValueError("GLB round-trip changed material or texture observations.")
        weight_error = _weight_error(expected["skin"], actual["skin"], tolerance)
        if weight_error > WEIGHT_TOLERANCE:
            raise ValueError(f"GLB round-trip changed skin weights: {weight_error:.6g}.")
        return {
            "schema_version": 1, "passed": True, "sha256": sha256,
            "sample_count": 1 + len(pose_errors), "clip_count": len(clips),
            "position_tolerance": tolerance, "max_rest_error": rest_error,
            "max_deformation_error": max_pose_error, "max_weight_error": weight_error,
            "max_duration_error_seconds": duration_error,
            "duration_tolerance_seconds": 1.0 / (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base),
            "sampling": "rest plus five matched integer-frame samples per clip",
            "rest_origin": "first clip origin" if clips else "static scene",
            "morph_target_count": actual["morph_count"],
            "scope": "pipeline-output-to-export; not anatomical or source-import certification",
        }
    finally:
        cleanup_imported_data(snapshot)
