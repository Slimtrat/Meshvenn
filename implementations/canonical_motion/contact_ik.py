"""Opt-in baked surface-feedback leg IK; flat rest floor, no live constraints.

Preserves the source's relative foot path, including treadmill travel. It does
not replace uncertain source contacts with a fictitious world-space foot lock.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from ...core.motion_contacts import SIDES, contact_windows, blended_contacts
from ...core.two_bone_ik import solve_two_bone
from .retarget import _base_pose_matrix, _make_quaternion_continuous, _set_linear_interpolation

MAX_ITERATIONS = 8
SURFACE_TOLERANCE = 1e-5
# A small skin stand-off prevents the curved sole trajectory between baked
# rotations from dipping through a plane touched exactly at the keys. This is
# a geometric clearance, not a contact detector or a guarantee of collision.
FLOOR_CLEARANCE = .002


def validate_contact_target(rig):
    arm = rig.armature_object
    linear = arm.matrix_world.to_3x3()
    columns = tuple(linear.col)
    lengths = tuple(column.length for column in columns)
    if (not all(math.isfinite(v) and v > 1e-10 for v in lengths) or linear.determinant() <= 0
            or max(lengths) - min(lengths) > max(lengths) * 1e-6
            or any(abs(columns[i].dot(columns[j])) > max(lengths) ** 2 * 1e-6 for i,j in ((0,1),(0,2),(1,2)))):
        raise ValueError("Contact IK requires a positive uniform armature transform, without shear")
    for side in SIDES:
        names = tuple(rig.semantic_bones[f"{part}.{side}"] for part in ("thigh", "shin", "foot"))
        bones = tuple(arm.data.bones[name] for name in names)
        if any(not math.isfinite(bone.length) or bone.length <= 1e-10
               or not bone.use_inherit_rotation or bone.inherit_scale != "FULL" for bone in bones):
            raise ValueError("Contact IK requires nonzero chains with full rotation/scale inheritance")
        for parent, child in zip(bones,bones[1:]):
            if child.parent != parent or (parent.tail_local-child.head_local).length > parent.length * 1e-5:
                raise ValueError("Contact IK requires contiguous thigh/shin/foot chains")
    if any(bone.constraints for bone in arm.pose.bones):
        raise ValueError("Contact IK does not support pre-existing pose constraints")
    if arm.animation_data and arm.animation_data.drivers:
        raise ValueError("Contact IK does not support pre-existing armature drivers")


def _world_rotation(arm, name):
    return (arm.matrix_world @ arm.pose.bones[name].matrix).to_quaternion()


def _set_world_rotation(arm, name, rotation):
    base = (arm.matrix_world @ _base_pose_matrix(arm, name)).to_quaternion()
    arm.pose.bones[name].rotation_quaternion = (base.inverted() @ rotation).normalized()
    bpy.context.view_layer.update()


def _joints(arm, names):
    return tuple(arm.matrix_world @ arm.pose.bones[name].head for name in names)


def _move_ankle(arm, names, goal, foot_rotation):
    hip, knee, ankle = _joints(arm, names)
    solution = solve_two_bone(tuple(hip), tuple(knee), tuple(ankle), tuple(goal))
    desired_knee, desired_ankle = Vector(solution.knee), Vector(solution.ankle)
    delta = (knee - hip).rotation_difference(desired_knee - hip)
    _set_world_rotation(arm, names[0], delta @ _world_rotation(arm, names[0]))
    _, knee, ankle = _joints(arm, names)
    delta = (ankle - knee).rotation_difference(desired_ankle - knee)
    _set_world_rotation(arm, names[1], delta @ _world_rotation(arm, names[1]))
    _set_world_rotation(arm, names[2], foot_rotation)
    return solution.reach_error


def bake_contact_ik(rig, baked, source, surface):
    arm = rig.armature_object
    arm.animation_data.action = baked.action
    arm.animation_data.use_nla = False
    runs = {side: contact_windows(source, side) for side in SIDES}
    names = {side: tuple(rig.semantic_bones[f"{part}.{side}"] for part in ("thigh", "shin", "foot")) for side in SIDES}
    # Freeze uncorrected FK anchors BEFORE any keys are edited.
    anchors = {}
    for side in SIDES:
        for run in runs[side]:
            bpy.context.scene.frame_set(source["samples"][run[0]]["frame"])
            bpy.context.view_layer.update()
            anchors[side, run[0]] = surface.observe()[side]["centroid"]
    previous = {}
    observations = []
    for index, sample in enumerate(source["samples"]):
        frame = sample["frame"]
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        frame_observations, frame_goals = [], {}
        for side in SIDES:
            blends, strength = blended_contacts(index, runs[side], source["fps"])
            if not blends: continue
            fk = surface.observe()[side]
            # Outside a source window, fade to its endpoint instead of
            # inventing extrapolated source contacts during flight.
            desired_xy, desired_z = [0.,0.], 0.
            for run, weight in blends:
                source_index = min(run[-1], max(run[0], index))
                before = source["samples"][run[0]]["feet"][side]
                now = source["samples"][source_index]["feet"][side]
                anchor = anchors[side, run[0]]
                for axis in (0,1): desired_xy[axis] += weight*(anchor[axis]+now["centroid"][axis]-before["centroid"][axis])
                desired_z += weight*max(FLOOR_CLEARANCE,now["min_z"])
            goal_xy = tuple(fk["centroid"][i] + strength * (desired_xy[i] - fk["centroid"][i]) for i in (0, 1))
            goal_z = fk["min_z"] + strength * (desired_z - fk["min_z"])
            frame_goals[side] = (goal_xy, goal_z)
            foot_rotation = _world_rotation(arm, names[side][2])
            reach_error = 0.
            for iteration in range(MAX_ITERATIONS):
                measured = surface.observe()[side]
                delta = Vector((goal_xy[0] - measured["centroid"][0],
                                goal_xy[1] - measured["centroid"][1], goal_z - measured["min_z"]))
                if delta.length <= SURFACE_TOLERANCE: break
                ankle = _joints(arm, names[side])[2]
                reach_error = max(reach_error, _move_ankle(arm, names[side], ankle + delta * surface.height, foot_rotation))
            measured = surface.observe()[side]
            frame_observations.append({"frame": frame, "side": side, "strength": strength,
                                 "windows": [{"frame_start": source["samples"][run[0]]["frame"],
                                              "frame_end": source["samples"][run[-1]]["frame"],"weight":weight}
                                             for run,weight in blends],
                                 "iterations": iteration + 1,
                                 "reach_error_in_heights": reach_error / surface.height,
                                 "surface_error_in_heights": math.hypot(goal_xy[0] - measured["centroid"][0],
                                                                       goal_xy[1] - measured["centroid"][1], goal_z - measured["min_z"])})
        if frame_observations:
            final = surface.observe()
            for observed in frame_observations:
                side = observed["side"]
                xy, z = frame_goals[side]
                measured = final[side]
                observed["surface_error_in_heights"] = math.hypot(xy[0] - measured["centroid"][0],
                                                               xy[1] - measured["centroid"][1], z - measured["min_z"])
                observed["status"] = "converged" if observed["surface_error_in_heights"] <= SURFACE_TOLERANCE else "limited"
            observations.extend(frame_observations)
        for side in SIDES:
            for name in names[side]:
                bone = arm.pose.bones[name]
                bone.rotation_quaternion = _make_quaternion_continuous(bone.rotation_quaternion, previous.get(name))
                bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=name)
                previous[name] = bone.rotation_quaternion.copy()
    _set_linear_interpolation(baked.action)
    return {"clip": baked.name, "source_windows": {side: len(run) for side, run in runs.items()},
            "floor_clearance_in_heights": FLOOR_CLEARANCE,
            "sole_probe_counts": {side: len(patch) for side, patch in surface.patches.items()},
            "max_surface_error_in_heights": max((o["surface_error_in_heights"] for o in observations), default=None),
            "max_reach_error_in_heights": max((o["reach_error_in_heights"] for o in observations), default=None),
            "limited_sample_count": sum(o["status"] == "limited" for o in observations),
            "observations": observations}
