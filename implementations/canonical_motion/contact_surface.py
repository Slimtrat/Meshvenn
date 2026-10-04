"""Sole-patch observations for production MOTION, supporting split meshes.

Target patches use generated leg-chain weights, never the source's labels or
vertex positions. Coincident UV seam positions carry one equal-weight vote.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Matrix

from ...core.motion_contacts import SIDES


class SoleSurface:
    def __init__(self, meshes, armature, roles, *, target=False):
        self.meshes = tuple(meshes)
        points = {(obj, v.index): tuple(obj.matrix_world @ v.co) for obj in self.meshes for v in obj.data.vertices}
        if not points or any(not all(math.isfinite(v) for v in p) for p in points.values()):
            raise ValueError("Contact IK requires finite bound rest geometry")
        minimum = tuple(min(p[i] for p in points.values()) for i in range(3))
        maximum = tuple(max(p[i] for p in points.values()) for i in range(3))
        self.height = maximum[2] - minimum[2]
        if self.height <= 0:
            raise ValueError("Contact IK requires positive rest-mesh height")
        self.origin = ((minimum[0] + maximum[0]) / 2, (minimum[1] + maximum[1]) / 2, minimum[2])
        self.patches = {}
        for side in SIDES:
            root = armature.data.bones[roles[f"foot.{side}"]]
            family = {root.name, *(bone.name for bone in root.children_recursive)}
            if target: family.update(roles[f"{part}.{side}"] for part in ("thigh", "shin"))
            patch = {}
            for obj in self.meshes:
                groups = {g.index for g in obj.vertex_groups if g.name in family}
                for vertex in obj.data.vertices:
                    point = points[obj, vertex.index]
                    if (point[2] - minimum[2]) / self.height > .02:
                        continue
                    if sum(g.weight for g in vertex.groups if g.group in groups) < .7:
                        continue
                    key = tuple(round((v - o) / self.height, 7) for v, o in zip(point, self.origin))
                    patch.setdefault(key, []).append((obj, vertex.index))
            if len(patch) < 3:
                raise ValueError(f"Contact IK needs three distinct confidently weighted sole positions: {side}")
            self.patches[side] = tuple(patch.values())
        self.indices = {obj: set() for obj in self.meshes}
        for patch in self.patches.values():
            for members in patch:
                for obj, index in members: self.indices[obj].add(index)

    def observe(self):
        points = {}
        graph = bpy.context.evaluated_depsgraph_get()
        for obj, indices in self.indices.items():
            evaluated = obj.evaluated_get(graph)
            mesh = evaluated.to_mesh()
            try:
                if len(mesh.vertices) != len(obj.data.vertices):
                    raise ValueError("Contact IK cannot track topology-changing modifiers")
                for index in indices:
                    point = evaluated.matrix_world @ mesh.vertices[index].co
                    if not all(math.isfinite(v) for v in point):
                        raise ValueError("Contact IK observed nonfinite geometry")
                    points[obj, index] = tuple((v - o) / self.height for v, o in zip(point, self.origin))
            finally:
                evaluated.to_mesh_clear()
        feet = {}
        for side, patch in self.patches.items():
            positions = [tuple(sum(points[obj, index][axis] for obj, index in members) / len(members)
                               for axis in range(3)) for members in patch]
            feet[side] = {"centroid": tuple(sum(p[axis] for p in positions) / len(positions) for axis in range(3)),
                          "min_z": min(p[2] for p in positions)}
        return feet


def observe_source_clip(surface, armature, action, fps):
    animation = armature.animation_data_create()
    animation.action = None
    animation.use_nla = False
    for bone in armature.pose.bones: bone.matrix_basis = Matrix.Identity(4)
    animation.action = action
    armature.data.pose_position = "POSE"
    start, end = math.floor(action.frame_range[0]), math.ceil(action.frame_range[1])
    if end <= start:
        raise ValueError("Contact IK source needs an increasing frame range")
    samples = []
    for frame in range(start, end + 1):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        samples.append({"frame": frame, "feet": surface.observe()})
    return {"name": action.name, "frame_start": start, "frame_end": end, "fps": fps, "samples": samples}
