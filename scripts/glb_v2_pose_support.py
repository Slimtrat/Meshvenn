"""State-restoring bilateral limb-joint probes for the GLB rig benchmark."""

from __future__ import annotations

from contextlib import contextmanager
import math

import bpy
from mathutils import Matrix, Vector

from scripts.glb_v2_pose_metrics import joint_edge_summary, pose_quality_summary


def evaluated_positions(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return tuple(tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


@contextmanager
def rotated_bone(armature, name, degrees, axis, *, world_space=False):
    """Apply a delta rotation without changing Euler/quaternion/axis-angle mode."""
    bone = armature.pose.bones[name]
    basis = bone.matrix_basis.copy()
    try:
        direction = Vector(axis)
        if world_space:
            frame = armature.matrix_world.to_3x3() @ bone.matrix.to_3x3()
            direction = frame.inverted() @ direction
        rotation = Matrix.Rotation(math.radians(degrees), 4, direction.normalized())
        bone.matrix_basis = basis @ rotation
        bpy.context.view_layer.update()
        yield
    finally:
        bone.matrix_basis = basis
        bpy.context.view_layer.update()


def pose_quality(mesh, armature, regions, *, hinges=False):
    rest = evaluated_positions(mesh)
    height = max(p[2] for p in rest)-min(p[2] for p in rest)
    mesh.data.calc_loop_triangles()
    triangles = tuple(tuple(t.vertices) for t in mesh.data.loop_triangles)
    poses = []
    probes = (("arm","upper_arm",(("Y",(0,1,0),60),("Z",(0,0,1),60))),
              ("leg","thigh",(("X",(1,0,0),60),("Y",(0,1,0),35))))
    if hinges:
        probes = (("arm","forearm",(("Y",(0,1,0),45),("Y",(0,1,0),90),
                                     ("Z",(0,0,1),45),("Z",(0,0,1),90))),
                  ("leg","shin",(("X",(1,0,0),45),("X",(1,0,0),90))))
    for family,root,axes in probes:
        for side,opposite in (("L","R"),("R","L")):
            name = f"{root}.{side}"
            center = tuple(armature.matrix_world @ armature.pose.bones[name].head)
            for axis,direction,angle in axes:
                for sign in (-1,1):
                    with rotated_bone(armature,name,sign*angle,direction,world_space=True):
                        posed = evaluated_positions(mesh)
                    edges = joint_edge_summary(rest,posed,triangles,center,height,touching=hinges)
                    def mean(label):
                        indices = regions[f"{family}.{label}"]
                        return sum(math.dist(rest[i],posed[i]) for i in indices)/len(indices)/height
                    poses.append({"id": f"{name}/{axis}/{sign*angle:+d}",
                                  "bone": name,"world_axis": axis,"angle_degrees": sign*angle,
                                  "joint_edges": edges,
                                  "posed_mean_displacement_in_heights": mean(side),
                                  "opposite_mean_displacement_in_heights": mean(opposite)})
    return {"schema_version": 2, "scope": "local surface edge distortion; not anatomy, volume or collisions",
            "edge_selection": "at least one endpoint near joint" if hinges else "both endpoints near joint",
            "joint_radius_in_heights": .12, **pose_quality_summary(poses), "poses": poses}
