"""Deterministic, scale-normalized 3D surface comparison for GLB benchmarks.

This module runs inside Blender. A common world-space bounding-box convention
centres each mesh and divides by its longest extent; no rotation or ICP is
allowed, so wrong proportions and orientation remain visible in the score.
"""

from __future__ import annotations

import bisect
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


SAMPLE_COUNT = 4096
F_SCORE_DISTANCE = 0.05
DETAIL_DISTANCES = (0.005, 0.01, 0.02)
MIN_TRIANGLE_AREA = 1e-12


def _triangles_from_glb(path: Path) -> tuple[list[tuple[Vector, Vector, Vector]], tuple[float, float, float]]:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    triangles = []
    points = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        vertices = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
        points.extend(vertices)
        for face in mesh.loop_triangles:
            triangles.append(tuple(vertices[index].copy() for index in face.vertices))
    if not triangles or not points:
        raise ValueError(f"GLB has no triangle surface: {path}")
    low = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    extent = high - low
    longest = max(extent)
    if not math.isfinite(longest) or longest <= 0.0:
        raise ValueError(f"GLB has degenerate bounds: {path}")
    center = (low + high) * 0.5
    normalized = [tuple((vertex - center) / longest for vertex in triangle) for triangle in triangles]
    return normalized, tuple(float(value / longest) for value in extent)


def _surface_samples(triangles: list[tuple[Vector, Vector, Vector]], count: int,
                     seed: int) -> list[tuple[Vector, Vector]]:
    cumulative = []
    usable = []
    total = 0.0
    for triangle in triangles:
        a, b, c = triangle
        area = (b - a).cross(c - a).length * 0.5
        if not math.isfinite(area) or area <= MIN_TRIANGLE_AREA:
            continue
        total += area
        cumulative.append(total)
        usable.append(triangle)
    if not usable:
        raise ValueError("Surface has no nondegenerate triangles")
    rng = random.Random(seed)
    samples = []
    for _ in range(count):
        index = min(bisect.bisect_left(cumulative, rng.random() * total), len(usable) - 1)
        a, b, c = usable[index]
        u = math.sqrt(rng.random())
        v = rng.random()
        samples.append(((1.0 - u) * a + u * (1.0 - v) * b + u * v * c,
                        (b - a).cross(c - a).normalized()))
    return samples


def _sample_surface(triangles: list[tuple[Vector, Vector, Vector]], count: int, seed: int) -> list[Vector]:
    # Keep the historical samples, seeds and sampled-point metric unchanged.
    return [point for point, _normal in _surface_samples(triangles, count, seed)]


def _nearest_distances(source: list[Vector], target: list[Vector]) -> list[float]:
    tree = KDTree(len(target))
    for index, point in enumerate(target):
        tree.insert(point, index)
    tree.balance()
    return [tree.find(point)[2] for point in source]


def _usable_triangles(triangles):
    usable = []
    for triangle in triangles:
        if len(triangle) != 3 or any(len(point) != 3 or any(
                not math.isfinite(value) for value in point) for point in triangle):
            raise ValueError("Surface triangles must contain finite 3D points")
        a, b, c = triangle
        area = (b - a).cross(c - a).length * 0.5
        if not math.isfinite(area):
            raise ValueError("Surface triangle area must be finite")
        if area > MIN_TRIANGLE_AREA:
            usable.append(triangle)
    if not usable:
        raise ValueError("Surface has no nondegenerate triangles")
    return usable


def _surface_tree(triangles):
    # Feed the exact exported loop triangles, not BVH polygon tessellation.
    vertices = [point for triangle in triangles for point in triangle]
    faces = [(index, index + 1, index + 2) for index in range(0, len(vertices), 3)]
    return BVHTree.FromPolygons(vertices, faces, all_triangles=True, epsilon=0.0)


def _surface_observations(samples, tree):
    observations = []
    for point, source_normal in samples:
        nearest, target_normal, _index, distance = tree.find_nearest(point)
        if nearest is None or distance is None or not math.isfinite(distance):
            raise ValueError("Surface BVH failed to return a finite nearest distance")
        dot = max(-1.0, min(1.0, source_normal.dot(target_normal)))
        observations.append((float(distance), float(dot)))
    return observations


def _distance_summary(distances):
    ordered = sorted(distances)
    return {"mean": math.fsum(distances) / len(distances),
            "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
            "max": ordered[-1]}


def _normal_summary(observations):
    # Face-normal agreement is meaningful locally, not between distant shapes.
    matched = [dot for distance, dot in observations if distance <= DETAIL_DISTANCES[-1]]
    angles = sorted(math.degrees(math.acos(dot)) for dot in matched)
    return {
        "maximum_correspondence_distance": DETAIL_DISTANCES[-1],
        "correspondence_count": len(matched),
        "correspondence_fraction": len(matched) / len(observations),
        "signed_dot_mean": math.fsum(matched) / len(matched) if matched else None,
        "absolute_dot_mean": math.fsum(abs(dot) for dot in matched) / len(matched) if matched else None,
        "angle_degrees_p95": angles[math.ceil(0.95 * len(angles)) - 1] if angles else None,
        "opposed_fraction": sum(dot < 0.0 for dot in matched) / len(matched) if matched else None,
    }


def _triangle_topology(triangles):
    """Exact-position seam weld; report edge and vertex-fan defects, not repair."""
    positions, edges, incident = {}, {}, {}
    degenerate = face_count = 0
    for triangle in triangles:
        a, b, c = triangle
        if (b - a).cross(c - a).length * 0.5 <= MIN_TRIANGLE_AREA:
            degenerate += 1
            continue
        ids = [positions.setdefault(tuple(point), len(positions)) for point in triangle]
        face = face_count
        face_count += 1
        for vertex in ids:
            incident.setdefault(vertex, set()).add(face)
        for start, end in zip(ids, ids[1:] + ids[:1]):
            edge = (min(start, end), max(start, end))
            edges.setdefault(edge, []).append((face, 1 if start < end else -1))
    boundary = sum(len(rows) == 1 for rows in edges.values())
    nonmanifold = sum(len(rows) > 2 for rows in edges.values())
    winding = sum(len(rows) == 2 and rows[0][1] == rows[1][1] for rows in edges.values())
    adjacent, boundary_degrees, bad_vertices = {}, {}, set()
    for (start, end), rows in edges.items():
        if len(rows) == 1:
            for vertex in (start, end):
                boundary_degrees[vertex] = boundary_degrees.get(vertex, 0) + 1
        elif len(rows) == 2:
            first, second = rows[0][0], rows[1][0]
            for vertex in (start, end):
                adjacent.setdefault((vertex, first), set()).add(second)
                adjacent.setdefault((vertex, second), set()).add(first)
        else:
            bad_vertices.update((start, end))
    for vertex in range(len(positions)):
        pending = set(incident[vertex])
        stack = [pending.pop()]
        while stack:
            for other in adjacent.get((vertex, stack.pop()), ()):
                if other in pending:
                    pending.remove(other)
                    stack.append(other)
        if pending or boundary_degrees.get(vertex, 0) not in (0, 2):
            bad_vertices.add(vertex)
    return {"weld_convention": "exact world-space normalized positions",
            "triangle_count": len(triangles), "degenerate_triangle_count": degenerate,
            "unique_position_count": len(positions), "edge_count": len(edges),
            "boundary_edge_count": boundary, "nonmanifold_edge_count": nonmanifold,
            "inconsistent_winding_edge_count": winding,
            "nonmanifold_vertex_count": len(bad_vertices),
            "self_intersections_checked": False}


def compare_surface_bvh(reference_triangles, candidate_triangles, *, samples=SAMPLE_COUNT):
    """Scoring-only exact triangle distances in the existing normalized frame.

    Sampling is deterministic and area-weighted, but nearest points are on the
    complete opposite triangle surface, avoiding sample-density distance noise.
    Geometric normals diagnose winding/shape, not imported custom shading normals.
    No source geometry from this diagnostic enters the reconstruction pipeline.
    """
    if type(samples) is not int or samples < 128:
        raise ValueError("At least 128 integer surface samples are required")
    reference_usable = _usable_triangles(reference_triangles)
    candidate_usable = _usable_triangles(candidate_triangles)
    forward = _surface_observations(
        _surface_samples(reference_usable, samples, seed=2026), _surface_tree(candidate_usable))
    backward = _surface_observations(
        _surface_samples(candidate_usable, samples, seed=2026), _surface_tree(reference_usable))
    forward_distances = [distance for distance, _dot in forward]
    backward_distances = [distance for distance, _dot in backward]
    scores = []
    for threshold in DETAIL_DISTANCES:
        recall = sum(distance <= threshold for distance in forward_distances) / samples
        precision = sum(distance <= threshold for distance in backward_distances) / samples
        scores.append({"distance_threshold": threshold, "precision": precision,
                       "recall": recall, "fscore": 2 * precision * recall / (precision + recall)
                       if precision + recall else 0.0})
    return {
        "algorithm": "area-weighted deterministic samples to exact triangle BVH",
        "distance_units": "fraction of each model's independent longest world-space bbox extent",
        "maximum_distance_convention": "maximum observed sample distance; not exact Hausdorff distance",
        "sample_count_per_surface": samples,
        "reference_to_candidate": _distance_summary(forward_distances),
        "candidate_to_reference": _distance_summary(backward_distances),
        "symmetric_distance": _distance_summary(forward_distances + backward_distances),
        "fscore_by_threshold": scores,
        "normal_convention": "signed geometric face normals at nearest triangles; not shading normals",
        "reference_to_candidate_normals": _normal_summary(forward),
        "candidate_to_reference_normals": _normal_summary(backward),
        "reference_topology": _triangle_topology(reference_triangles),
        "candidate_topology": _triangle_topology(candidate_triangles),
    }


def compare_glb_surfaces(reference_path: Path, candidate_path: Path, *, samples: int = SAMPLE_COUNT) -> dict:
    """Return symmetric Chamfer and F-score on sampled 3D triangle surfaces."""
    if samples < 128:
        raise ValueError("At least 128 surface samples are required")
    reference_triangles, reference_extents = _triangles_from_glb(reference_path)
    candidate_triangles, candidate_extents = _triangles_from_glb(candidate_path)
    reference = _sample_surface(reference_triangles, samples, seed=2026)
    candidate = _sample_surface(candidate_triangles, samples, seed=2026)
    forward = _nearest_distances(reference, candidate)
    backward = _nearest_distances(candidate, reference)
    recall = sum(distance <= F_SCORE_DISTANCE for distance in forward) / samples
    precision = sum(distance <= F_SCORE_DISTANCE for distance in backward) / samples
    f_score = 2.0 * recall * precision / (recall + precision) if recall + precision else 0.0
    all_distances = sorted(forward + backward)
    return {
        "normalization": "independent world-space bbox center and longest extent; no rotation or ICP",
        "sample_count_per_surface": samples,
        "distance_threshold": F_SCORE_DISTANCE,
        "reference_normalized_extents": reference_extents,
        "candidate_normalized_extents": candidate_extents,
        "max_extent_error": max(abs(a - b) for a, b in zip(reference_extents, candidate_extents)),
        "symmetric_chamfer_mean": (sum(forward) + sum(backward)) / (2.0 * samples),
        "symmetric_distance_p95": all_distances[int(0.95 * (len(all_distances) - 1))],
        "surface_precision": precision,
        "surface_recall": recall,
        "surface_fscore": f_score,
        "surface_bvh": compare_surface_bvh(reference_triangles, candidate_triangles, samples=samples),
    }
