"""Shared measurements for the end-to-end GLB V2 character benchmark."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


Point3 = tuple[float, float, float]


def normalized_landmarks(
    landmarks: Mapping[str, Sequence[float]],
    vertices: Sequence[Sequence[float]],
) -> dict[str, Point3]:
    """Express landmarks in a translation- and height-normalized body frame."""
    if not vertices:
        raise ValueError("No mesh vertices to establish a landmark frame")
    points = [tuple(float(value) for value in vertex) for vertex in vertices]
    if any(len(point) != 3 or any(not math.isfinite(value) for value in point) for point in points):
        raise ValueError("Mesh vertices must contain three finite coordinates")
    low = tuple(min(point[axis] for point in points) for axis in range(3))
    high = tuple(max(point[axis] for point in points) for axis in range(3))
    height = high[2] - low[2]
    if not math.isfinite(height) or height <= 0.0:
        raise ValueError("Mesh height must be positive and finite")
    center_x = (low[0] + high[0]) * 0.5
    center_y = (low[1] + high[1]) * 0.5
    result: dict[str, Point3] = {}
    for name, point in landmarks.items():
        values = tuple(float(value) for value in point)
        if len(values) != 3 or any(not math.isfinite(value) for value in values):
            raise ValueError(f"Invalid rig landmark: {name}")
        result[str(name)] = (
            (values[0] - center_x) / height,
            (values[1] - center_y) / height,
            (values[2] - low[2]) / height,
        )
    return result


def assert_unrigged_mesh(mesh: object) -> None:
    """Reject accidental leakage of source rigging into the generated mesh."""
    if getattr(mesh, "parent", None) is not None:
        raise AssertionError("Reconstructed mesh unexpectedly has a parent")
    if any(getattr(modifier, "type", None) == "ARMATURE" for modifier in mesh.modifiers):
        raise AssertionError("Reconstructed mesh unexpectedly has an armature modifier")
    if len(mesh.vertex_groups):
        raise AssertionError("Reconstructed mesh unexpectedly has source vertex groups")


def connectivity_summary(vertices, polygons) -> dict:
    """Measure real surface components, welding exact glTF seam duplicates."""
    unique, indices = {}, []
    for vertex in vertices:
        key = tuple(vertex)
        indices.append(unique.setdefault(key, len(unique)))
    neighbors = [set() for _ in unique]
    for face in polygons:
        welded = [indices[i] for i in face]
        for a,b in zip(welded,welded[1:]+welded[:1]):
            neighbors[a].add(b)
            neighbors[b].add(a)
    pending = set(range(len(neighbors)))
    counts = []
    while pending:
        stack = [pending.pop()]
        count = 0
        while stack:
            vertex = stack.pop()
            count += 1
            for other in neighbors[vertex]:
                if other in pending:
                    pending.remove(other)
                    stack.append(other)
        counts.append(count)
    return {"component_count": len(counts), "unique_position_count": len(unique),
            "component_sizes": sorted(counts, reverse=True)}

