"""Explicit capture-frame/LBS math for producer diagnostics, not engine policy."""

from __future__ import annotations

import numpy as np

MATRIX_LAYOUT = "basis X column xyz, basis Y column xyz, basis Z column xyz, origin xyz; implicit last row 0 0 0 1"
POSE_CONVENTION = "Pose is the complete parent-local transform, not a rest-relative delta; RestRelative = inverse(Rest) * Pose"
AXES = np.array(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)), dtype=float)


def matrix(values):
    if len(values) != 12 or any(type(x) not in (int, float) for x in values):
        raise ValueError("Require twelve finite basis-column/origin numbers")
    result = np.vstack((np.array(values, dtype=float).reshape(4, 3).T, (0, 0, 0, 1)))
    if not np.isfinite(result).all() or np.linalg.det(result[:3, :3]) <= 1e-10:
        raise ValueError("Nonfinite, singular or mirrored capture transform")
    return result


def accumulated(bones, names, parents, key):
    if len(bones) != len(names) or len(parents) != len(names):
        raise ValueError("Capture hierarchy size differs from the native skin")
    result = []
    for i, bone in enumerate(bones):
        if (
            bone["Index"] != i
            or bone["Name"] != names[i]
            or bone["Parent"] != parents[i]
            or type(bone["Parent"]) is not int
            or not -1 <= bone["Parent"] < i
        ):
            raise ValueError(
                "Capture joint identity/order/hierarchy differs from the native skin"
            )
        local = matrix(bone[key])
        result.append(result[bone["Parent"]] @ local if bone["Parent"] >= 0 else local)
    return np.array(result)


def verify_frames(frames, tolerance=2e-6):
    for key, target in (
        ("MeshAncestors", "MeshWorld"),
        ("SkeletonAncestors", "SkeletonWorld"),
    ):
        previous = np.identity(4)
        if not frames[key]:
            raise ValueError("Capture omitted the complete ancestor chain")
        for ancestor in reversed(frames[key]):
            previous = previous @ matrix(ancestor["Local"])
            if np.max(abs(previous - matrix(ancestor["World"]))) > tolerance:
                raise ValueError(
                    "Ancestor local/world transforms contradict each other"
                )
        if np.max(abs(previous - matrix(frames[target]))) > tolerance:
            raise ValueError(
                "Ancestor chain does not reproduce the declared object frame"
            )
    relative = np.linalg.inv(matrix(frames["SkeletonWorld"])) @ matrix(
        frames["MeshWorld"]
    )
    if np.max(abs(relative - matrix(frames["MeshToSkeleton"]))) > tolerance:
        raise ValueError("Mesh-to-skeleton frame is inconsistent")
    return np.linalg.inv(matrix(frames["MeshWorld"])) @ matrix(frames["SkeletonWorld"])


def unit(rows):
    return rows / np.maximum(np.linalg.norm(rows, axis=-1, keepdims=True), 1e-30)


def angles(a, b):
    return np.degrees(np.arccos(np.clip(np.sum(unit(a) * unit(b), axis=-1), -1, 1)))


def summary(values):
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("Cannot summarize empty/nonfinite measurements")
    return {
        "max": float(np.max(values)),
        "p99": float(np.quantile(values, 0.99)),
        "p95": float(np.quantile(values, 0.95)),
        "median": float(np.median(values)),
    }


def lbs(palette, points, normals, joints, weights):
    if (
        len(points) != len(normals)
        or joints.shape != weights.shape
        or len(joints) != len(points)
        or np.min(joints) < 0
        or np.max(joints) >= len(palette)
        or not np.isfinite(weights).all()
        or np.min(weights) < 0
    ):
        raise ValueError("Invalid bounded LBS arrays")
    blend = np.einsum("nk,nkij->nij", weights, palette[joints])
    homogeneous = np.column_stack((points, np.ones(len(points))))
    return (
        np.einsum("nij,nj->ni", blend, homogeneous)[:, :3],
        unit(np.einsum("nij,nj->ni", blend[:, :3, :3], normals)),
    )


def oriented(triangle):
    triangle = tuple(triangle)
    return min(triangle, triangle[1:] + triangle[:1], triangle[2:] + triangle[:2])


def coherence(rest, posed, normals, triangles, arm_mask):
    """Shading/geometric disagreement is an observation, not an inversion proof."""
    face = unit(
        np.cross(
            posed[triangles[:, 1]] - posed[triangles[:, 0]],
            posed[triangles[:, 2]] - posed[triangles[:, 0]],
        )
    )
    dot = np.sum(face * unit(normals[triangles].mean(axis=1)), axis=1)
    before = np.linalg.norm(rest[triangles[:, 1]] - rest[triangles[:, 0]], axis=1)
    after = np.linalg.norm(posed[triangles[:, 1]] - posed[triangles[:, 0]], axis=1)
    return {
        "arm_triangles": int(arm_mask.sum()),
        "arm_facing_negative": int(np.sum(dot[arm_mask] < 0)),
        "all_facing_negative": int(np.sum(dot < 0)),
        "arm_normal_geometric_angle_deg": summary(
            np.degrees(np.arccos(np.clip(dot[arm_mask], -1, 1)))
        ),
        "arm_edge_ratio": summary((after / np.maximum(before, 1e-15))[arm_mask]),
    }
