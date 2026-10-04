"""Local geometric distortion, not an anatomical or collision certificate."""

from __future__ import annotations

import math


# Fixture regression budgets, not universal humanoid suitability thresholds.
# Tuple: p95 log strain, worst log strain, collapsed and stretched fractions.
POSE_BUDGETS = {
    "rigged_figure": (.43, .65, 0.0, 0.0),
    "quaternius_human": (1.18, 1.65, .018, .022),
    "quaternius_ual1": (.40, 1.95, .002, .002),
}
HINGE_BUDGETS = {
    "rigged_figure": (.35, .36, 0.0, 0.0),
    "quaternius_human": (.39, .58, 0.0, 0.0),
    "quaternius_ual1": (.395, .63, 0.0, 0.0),
}


def pose_acceptance(asset, *, hinges=False):
    p95,worst,collapsed,stretched = (HINGE_BUDGETS if hinges else POSE_BUDGETS)[asset]
    return {"worst_p95_abs_log_length_ratio": p95,
            "worst_abs_log_length_ratio": worst,
            "worst_collapsed_fraction": collapsed,
            "worst_stretched_fraction": stretched,
            "worst_opposite_mean_displacement_in_heights": .0005,
            "min_posed_mean_displacement_in_heights": .01}


def check_pose_quality(report, acceptance, *, expected_count=16):
    if report["pose_count"] != expected_count:
        raise AssertionError(f"Missing bilateral pose probes: expected {expected_count}")
    for name,limit in acceptance.items():
        value = report[name]
        if not math.isfinite(value) or value < 0:
            raise AssertionError(f"Invalid pose measurement: {name}")
        failed = value < limit if name.startswith("min_") else value > limit
        if failed:
            raise AssertionError(f"Pose quality budget exceeded: {name} = {value:.6f}, limit = {limit}")


def check_pose_roundtrip(before, after, *, expected_count=16):
    """Compare identical world-axis probes, not import-dependent bone rolls."""
    original = {p["id"]: p for p in before["poses"]}
    imported = {p["id"]: p for p in after["poses"]}
    if len(original) != expected_count or original.keys() != imported.keys() or any(
        len(report["poses"]) != expected_count for report in (before,after)
    ):
        raise AssertionError("GLB changed the set of deformation probes")
    for name,a in original.items():
        b = imported[name]
        for field in ("posed_mean_displacement_in_heights", "opposite_mean_displacement_in_heights"):
            if not math.isfinite(b[field]) or abs(a[field]-b[field]) > 1e-4:
                raise AssertionError(f"GLB changed pose response: {name}/{field}")
        for field,value in a["joint_edges"].items():
            tolerance = 0 if field == "edge_count" else .005
            if not math.isfinite(b["joint_edges"][field]) or abs(value-b["joint_edges"][field]) > tolerance:
                raise AssertionError(f"GLB changed local edge deformation: {name}/{field}")


def _points(values):
    points = tuple(tuple(float(v) for v in point) for point in values)
    if not points or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError("Expected nonempty finite 3D positions")
    return points


def joint_edge_summary(rest, posed, triangles, center, height, *, radius_in_heights=.12,
                       touching=False):
    """Measure unique surface edges around the rest joint.

    By default both endpoints must be near the joint. With touching=True,
    retain edges with at least one endpoint near it, including transitions
    between rings of a coarse mesh. Edges entirely outside are still excluded.

    Coincident seam vertices do not multiply edge samples. Degenerate/tiny
    rest edges are excluded, but collapsed posed edges remain failures.
    p95 is nearest-rank absolute log(length ratio), so stretching and
    compression are treated symmetrically, independent of world scale.
    """
    rest, posed = _points(rest), _points(posed)
    center = _points((center,))[0]
    if len(rest) != len(posed):
        raise ValueError("Pose changed topology")
    if not math.isfinite(height) or height <= 0 or not math.isfinite(radius_in_heights) or radius_in_heights <= 0:
        raise ValueError("Height and radius must be positive and finite")
    origin = tuple(min(p[i] for p in rest) for i in range(3))
    keys = [tuple(round((v-o)/height, 7) for v,o in zip(p,origin)) for p in rest]
    edges = {}
    for triangle in triangles:
        if len(triangle) != 3 or any(type(i) is not int or not 0 <= i < len(rest) for i in triangle):
            raise ValueError("Invalid triangle indices")
        for a,b in zip(triangle, (*triangle[1:],triangle[0])):
            distances = [math.dist(rest[i],center) for i in (a,b)]
            if (min(distances) if touching else max(distances)) > radius_in_heights*height:
                continue
            length = math.dist(rest[a],rest[b])
            if length <= height*1e-5:
                continue
            key = tuple(sorted((keys[a],keys[b])))
            # Retain the worst seam variant instead of silently hiding a tear.
            ratio = math.dist(posed[a],posed[b])/length
            if not math.isfinite(ratio):
                raise ValueError("Nonfinite edge deformation")
            strain = abs(math.log(max(ratio,1e-12)))
            if key not in edges or strain > edges[key][0]:
                edges[key] = (strain,ratio)
    if not edges:
        raise ValueError("No nondegenerate surface edges around joint")
    strains = sorted(value[0] for value in edges.values())
    ratios = [value[1] for value in edges.values()]
    return {
        "edge_count": len(edges),
        "p95_abs_log_length_ratio": strains[math.ceil(.95*len(strains))-1],
        "max_abs_log_length_ratio": strains[-1],
        "min_length_ratio": min(ratios), "max_length_ratio": max(ratios),
        "collapsed_fraction": sum(r < .25 for r in ratios)/len(ratios),
        "stretched_fraction": sum(r > 2 for r in ratios)/len(ratios),
    }


def pose_quality_summary(poses):
    if not poses or len({pose["id"] for pose in poses}) != len(poses):
        raise ValueError("Expected distinct pose samples")
    values = [pose["joint_edges"] for pose in poses]
    return {
        "pose_count": len(poses),
        "worst_p95_abs_log_length_ratio": max(v["p95_abs_log_length_ratio"] for v in values),
        "worst_abs_log_length_ratio": max(v["max_abs_log_length_ratio"] for v in values),
        "worst_collapsed_fraction": max(v["collapsed_fraction"] for v in values),
        "worst_stretched_fraction": max(v["stretched_fraction"] for v in values),
        "worst_opposite_mean_displacement_in_heights": max(p["opposite_mean_displacement_in_heights"] for p in poses),
        "min_posed_mean_displacement_in_heights": min(p["posed_mean_displacement_in_heights"] for p in poses),
    }
