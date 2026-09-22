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
from mathutils.kdtree import KDTree


SAMPLE_COUNT = 4096
F_SCORE_DISTANCE = 0.05


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


def _sample_surface(triangles: list[tuple[Vector, Vector, Vector]], count: int, seed: int) -> list[Vector]:
    cumulative = []
    usable = []
    total = 0.0
    for triangle in triangles:
        a, b, c = triangle
        area = (b - a).cross(c - a).length * 0.5
        if not math.isfinite(area) or area <= 1e-12:
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
        samples.append((1.0 - u) * a + u * (1.0 - v) * b + u * v * c)
    return samples


def _nearest_distances(source: list[Vector], target: list[Vector]) -> list[float]:
    tree = KDTree(len(target))
    for index, point in enumerate(target):
        tree.insert(point, index)
    tree.balance()
    return [tree.find(point)[2] for point in source]


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
    }
