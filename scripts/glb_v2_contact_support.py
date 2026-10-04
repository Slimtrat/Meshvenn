"""Observe fixed source-labelled sole surface patches, not bone endpoints.

Frozen normalized rest positions survive GLB vertex reordering/UV seams. No
labels, weights, source rig or contact observations are passed to the fitter.
"""
from __future__ import annotations

import math

import bpy
from mathutils.kdtree import KDTree

from scripts.glb_v2_contact_metrics import SIDES, dense_frames

MATCH_TOLERANCE = 1e-5


def _rest_geometry(mesh):
    points = [tuple(mesh.matrix_world @ v.co) for v in mesh.data.vertices]
    minimum = [min(p[i] for p in points) for i in range(3)]
    maximum = [max(p[i] for p in points) for i in range(3)]
    height = maximum[2] - minimum[2]
    if not math.isfinite(height) or height <= 0:
        raise AssertionError("Sole observations require positive rest-mesh height")
    origin = ((minimum[0] + maximum[0]) / 2, (minimum[1] + maximum[1]) / 2, minimum[2])
    return [tuple((v - o) / height for v, o in zip(p, origin)) for p in points], origin, height


def source_sole_probes(mesh, armature, roles):
    points, _, _ = _rest_geometry(mesh)
    families = {}
    for side in SIDES:
        root = armature.data.bones[roles[f"foot.{side}"]]
        names = {root.name, *(bone.name for bone in root.children_recursive)}
        families[side] = {g.index for g in mesh.vertex_groups if g.name in names}
    probes = {}
    for side in SIDES:
        selected = {tuple(round(v, 7) for v in points[vertex.index]) for vertex in mesh.data.vertices
                    if points[vertex.index][2] <= .02 and
                    sum(g.weight for g in vertex.groups if g.group in families[side]) >= .7}
        if len(selected) < 3:
            raise AssertionError(f"No confidently source-weighted sole patch: {side}")
        probes[side] = sorted(selected)
    if set(probes["L"]) & set(probes["R"]):
        raise AssertionError("Source sole patches overlap")
    return probes


def _match_probes(points, probes):
    tree = KDTree(len(points))
    for index, point in enumerate(points): tree.insert(point, index)
    tree.balance()
    result = {}
    used = set()
    for side, patch in probes.items():
        result[side] = []
        for point in patch:
            hits = tree.find_range(point, MATCH_TOLERANCE)
            indices = tuple(sorted(hit[1] for hit in hits))
            if not indices or used.intersection(indices):
                raise AssertionError(f"Missing or ambiguous frozen sole position: {side}/{point}")
            used.update(indices)
            result[side].append(indices)
    return result


def _evaluated_patch(mesh, indices, vertex_count):
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    surface = evaluated.to_mesh()
    try:
        if len(surface.vertices) != vertex_count:
            raise AssertionError("Contact observation changed mesh topology")
        return {index: tuple(evaluated.matrix_world @ surface.vertices[index].co) for index in indices}
    finally:
        evaluated.to_mesh_clear()


def observe_surfaces(mesh, armature, clips, probes, bind_action):
    rest, origin, height = _rest_geometry(mesh)
    matches = _match_probes(rest, probes)
    indices = {index for patch in matches.values() for group in patch for index in group}
    observed = []
    for clip in clips:
        bind_action(armature, clip["action"])
        samples = []
        for frame in dense_frames(clip["frame_start"], clip["frame_end"]):
            bpy.context.scene.frame_set(frame)
            bpy.context.view_layer.update()
            points = _evaluated_patch(mesh, indices, len(rest))
            feet = {}
            for side, patch in matches.items():
                # Average coincident rest vertices, then weight each unique
                # rest position equally, independent of UV seam duplication.
                positions = [tuple(sum((points[index][axis] - origin[axis]) / height for index in indices)
                                   / len(indices) for axis in range(3)) for indices in patch]
                feet[side] = {"centroid": [sum(p[i] for p in positions) / len(positions) for i in range(3)],
                              "min_z": min(p[2] for p in positions)}
            samples.append({"frame": frame, "feet": feet})
        observed.append({k: clip[k] for k in ("name", "frame_start", "frame_end", "fps")}
                        | {"samples": samples})
    return {"probes": probes, "clips": observed}
