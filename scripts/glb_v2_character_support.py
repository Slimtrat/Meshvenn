"""Shared measurements for the end-to-end GLB V2 character benchmark."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


Point3 = tuple[float, float, float]

DETAIL_SURFACE_DISTANCE = .01


def assert_detail_surface_quality(surface: Mapping, *, minimum_fscore: float = 0.) -> float | None:
    """Gate sampled distances to full triangles, independently of legacy F-score.

    One percent is relative to the existing independent longest-extent frame;
    this does not certify absolute scale, translation, topology or anatomy.
    """
    if type(minimum_fscore) not in (float, int) or not math.isfinite(minimum_fscore) or not 0 <= minimum_fscore <= 1:
        raise ValueError("Detail surface F-score must be in 0..1.")
    if minimum_fscore == 0:
        return None
    detail = surface.get("surface_bvh")
    if (not isinstance(detail, Mapping)
            or detail.get("algorithm") != "area-weighted deterministic samples to exact triangle BVH"
            or detail.get("distance_units") != "fraction of each model's independent longest world-space bbox extent"
            or type(detail.get("sample_count_per_surface")) is not int
            or detail["sample_count_per_surface"] < 128):
        raise AssertionError("Character detail surface metric has no valid triangle-distance evidence")
    scores = detail.get("fscore_by_threshold")
    if not isinstance(scores, (tuple, list)) or not scores:
        raise AssertionError("Character detail surface metric has no threshold scores")
    thresholds, selected = set(), None
    for row in scores:
        if not isinstance(row, Mapping):
            raise AssertionError("Character detail surface score is invalid")
        values = [row.get(key) for key in ("distance_threshold", "precision", "recall", "fscore")]
        if any(type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1 for value in values):
            raise AssertionError("Character detail surface scores must be finite fractions")
        threshold, precision, recall, score = values
        if threshold <= 0 or threshold in thresholds:
            raise AssertionError("Character detail surface thresholds must be positive and unique")
        thresholds.add(threshold)
        expected = 2 * precision * recall / (precision + recall) if precision + recall else 0.
        if not math.isclose(score, expected, rel_tol=0., abs_tol=1e-12):
            raise AssertionError("Character detail surface F-score contradicts precision/recall")
        if threshold == DETAIL_SURFACE_DISTANCE:
            selected = score
    if selected is None or selected < minimum_fscore:
        raise AssertionError(f"Character triangle-distance F-score at 1% fell below {minimum_fscore:.0%}")
    return float(selected)


def assert_refinement_quality(report: Mapping, *, min_roughness_reduction: float = 0.,
                              min_contour_reduction: float = 0.) -> None:
    """Fail opt-in finish gates independently from the existing geometry gates."""
    for threshold in (min_roughness_reduction,min_contour_reduction):
        if not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("Refinement reductions must be in 0..1.")
    if min_roughness_reduction == min_contour_reduction == 0:
        return
    if (report.get("algorithm") != "contour-taubin-v2"
            or not report.get("topology_preserved") or not report.get("face_orientation_preserved")):
        raise AssertionError("Character contour refinement or its safeguards are missing")
    for prefix,threshold in (("roughness",min_roughness_reduction),
                             ("mean_contour_residual",min_contour_reduction)):
        if threshold == 0:
            continue
        before = report.get(f"{prefix}_before_in_voxels")
        after = report.get(f"{prefix}_after_in_voxels")
        if (type(before) not in (float,int) or type(after) not in (float,int)
                or not math.isfinite(before) or not math.isfinite(after) or before <= 0 or after < 0):
            raise AssertionError(f"Character {prefix} reduction has no valid evidence")
        if after > before*(1-threshold):
            raise AssertionError(f"Character {prefix} reduction fell below {threshold:.0%}")
    if min_contour_reduction:
        total = report.get("contour_residual_sample_count")
        counts = [report.get(f"contour_residual_valid_samples_{phase}") for phase in ("before","after")]
        if (type(total) is not int or total <= 0 or any(type(n) is not int or n > total or n < .95*total for n in counts)):
            raise AssertionError("Character contour residual is not measurable on at least 95% of vertices")


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

