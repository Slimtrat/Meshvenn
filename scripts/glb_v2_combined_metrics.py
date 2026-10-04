"""Deterministic combined-pose cases and independent geometric regression gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math


# Separate fixture budgets for the new combined stress set. The original
# 16 root and 24 hinge probe budgets are intentionally unchanged.
COMBINED_BUDGETS = {
    "rigged_figure": (.56, .67, 0.0, 0.0),
    "quaternius_human": (.90, 1.18, 0.0, .022),
    "quaternius_ual1": (.40, 1.30, 0.0, .002),
}
_EDGE_FIELDS = {"edge_count", "p95_abs_log_length_ratio", "max_abs_log_length_ratio",
                "min_length_ratio", "max_length_ratio", "collapsed_fraction", "stretched_fraction"}


def _finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_sample_reference(reference):
    if set(reference) != {"height", "positions"} or not _finite_nonnegative(reference["height"]) or reference["height"] == 0:
        raise ValueError("Invalid combined-pose reference height")
    points = reference["positions"]
    if not 1 <= len(points) <= 80 or any(
        len(point) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
        for point in points
    ):
        raise ValueError("Expected 1 to 80 finite combined-pose reference points")


def _validate_edges(metrics):
    if set(metrics) != _EDGE_FIELDS or type(metrics["edge_count"]) is not int or metrics["edge_count"] <= 0:
        raise ValueError("Missing or invalid combined-pose edge measurement")
    if any(not _finite_nonnegative(value) for value in metrics.values()) or any(
        metrics[field] > 1 for field in ("collapsed_fraction", "stretched_fraction")
    ):
        raise ValueError("Invalid combined-pose edge measurement")
    if metrics["p95_abs_log_length_ratio"] > metrics["max_abs_log_length_ratio"] or metrics["min_length_ratio"] > metrics["max_length_ratio"]:
        raise ValueError("Inconsistent combined-pose edge measurement")


@dataclass(frozen=True)
class Rotation:
    bone: str
    world_axis: str
    degrees: int


@dataclass(frozen=True)
class CombinedCase:
    identifier: str
    rotations: tuple[Rotation, ...]
    active_regions: tuple[str, ...]


def combined_cases() -> tuple[CombinedCase, ...]:
    """32 single-chain + four same-side whole-body stress poses, parent first.

    Signed world-axis probes include non-anatomical directions. They are a
    reproducible stress set, not an animation library or range-of-motion claim.
    """
    chains = (
        ("arm", "upper_arm", "forearm", (
            ("reach", "Y", 45, "Y", 90),
            ("cross-plane", "Z", 60, "Y", 90),
            ("counter-bend", "Y", 60, "Y", -90),
            ("partial", "Z", 45, "Z", 45),
        )),
        ("leg", "thigh", "shin", (
            ("fold", "X", 60, "X", -90),
            ("abduct", "Y", 35, "X", 90),
            ("counter-bend", "X", -45, "X", 90),
            ("partial", "X", 45, "X", -45),
        )),
    )
    result = []
    for side in ("L", "R"):
        for sign in (-1, 1):
            for family, parent, child, variants in chains:
                for tag, parent_axis, parent_angle, child_axis, child_angle in variants:
                    result.append(CombinedCase(
                        f"{family}.{side}/{tag}/{sign:+d}",
                        (Rotation(f"{parent}.{side}", parent_axis, sign * parent_angle),
                         Rotation(f"{child}.{side}", child_axis, sign * child_angle)),
                        (f"{family}.{side}",),
                    ))
            result.append(CombinedCase(
                f"body.{side}/reach-fold/{sign:+d}",
                (Rotation(f"upper_arm.{side}", "Y", sign * 45),
                 Rotation(f"forearm.{side}", "Z", sign * 90),
                 Rotation(f"thigh.{side}", "X", sign * 45),
                 Rotation(f"shin.{side}", "X", sign * -90)),
                (f"arm.{side}", f"leg.{side}"),
            ))
    return tuple(result)


def combined_summary(cases):
    expected = {case.identifier: case for case in combined_cases()}
    if len(cases) != len(expected) or {case["id"] for case in cases} != expected.keys():
        raise ValueError("Missing or duplicated combined-pose case")
    edges, active, inactive = [], [], []
    for case in cases:
        spec = expected[case["id"]]
        if case["rotations"] != [asdict(rotation) for rotation in spec.rotations]:
            raise ValueError("Combined-pose rotations do not match the stress case")
        if set(case["joint_edges"]) != {rotation.bone for rotation in spec.rotations}:
            raise ValueError("Missing joint measurement in combined pose")
        response = case["region_response"]
        if set(response) != {"arm.L", "arm.R", "leg.L", "leg.R"}:
            raise ValueError("Missing limb response in combined pose")
        for label, value in response.items():
            if not _finite_nonnegative(value):
                raise ValueError("Invalid combined-pose movement")
            (active if label in spec.active_regions else inactive).append(value)
        for metrics in case["joint_edges"].values():
            _validate_edges(metrics)
        edges.extend(case["joint_edges"].values())
    return {
        "pose_count": len(cases), "joint_sample_count": len(edges),
        "worst_p95_abs_log_length_ratio": max(e["p95_abs_log_length_ratio"] for e in edges),
        "worst_abs_log_length_ratio": max(e["max_abs_log_length_ratio"] for e in edges),
        "worst_collapsed_fraction": max(e["collapsed_fraction"] for e in edges),
        "worst_stretched_fraction": max(e["stretched_fraction"] for e in edges),
        "min_active_mean_displacement_in_heights": min(active),
        "max_inactive_mean_displacement_in_heights": max(inactive),
    }


def _validate_report(report):
    summary = combined_summary(report["cases"])
    if any(not _finite_nonnegative(report.get(field)) or report[field] != value for field, value in summary.items()):
        raise AssertionError("Combined-pose summary does not match individual probes")
    validate_sample_reference(report["sample_reference"])
    count = len(report["sample_reference"]["positions"])
    for case in report["cases"]:
        points = case["sample_positions_in_heights"]
        if len(points) != count or any(
            len(point) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
            for point in points
        ):
            raise ValueError("Missing or invalid combined deformation sample")
    return summary


def combined_acceptance(asset):
    p95, worst, collapsed, stretched = COMBINED_BUDGETS[asset]
    return {"worst_p95_abs_log_length_ratio": p95,
            "worst_abs_log_length_ratio": worst,
            "worst_collapsed_fraction": collapsed,
            "worst_stretched_fraction": stretched,
            "min_active_mean_displacement_in_heights": .01,
            "max_inactive_mean_displacement_in_heights": .0005}


def check_combined_quality(report, acceptance):
    summary = _validate_report(report)
    if set(acceptance) != set(combined_acceptance("rigged_figure")):
        raise ValueError("Missing combined-pose quality budget")
    for field, limit in acceptance.items():
        if not _finite_nonnegative(limit):
            raise ValueError("Invalid combined-pose quality budget")
        value = summary[field]
        if (value < limit if field.startswith("min_") else value > limit):
            raise AssertionError(f"Combined pose quality exceeded: {field} = {value:.6f}, limit = {limit}")


def check_combined_roundtrip(before, after):
    """Compare every joint and sampled vertex, never an aggregate alone."""
    _validate_report(before)
    _validate_report(after)
    if before["sample_reference"] != after["sample_reference"]:
        raise AssertionError("GLB changed the combined-pose sample reference")
    imported = {case["id"]: case for case in after["cases"]}
    max_sample_error = 0.0
    for a in before["cases"]:
        b = imported[a["id"]]
        for label, value in a["region_response"].items():
            if not math.isfinite(b["region_response"][label]) or abs(value-b["region_response"][label]) > 1e-4:
                raise AssertionError(f"GLB changed combined limb response: {a['id']}/{label}")
        for joint, metrics in a["joint_edges"].items():
            for field, value in metrics.items():
                other = b["joint_edges"][joint][field]
                tolerance = 0 if field == "edge_count" else .005
                if not math.isfinite(other) or abs(value-other) > tolerance:
                    raise AssertionError(f"GLB changed combined joint distortion: {a['id']}/{joint}/{field}")
        for source, target in zip(a["sample_positions_in_heights"], b["sample_positions_in_heights"]):
            max_sample_error = max(max_sample_error, math.dist(source,target))
    if max_sample_error > 1e-4:
        raise AssertionError(f"GLB changed combined sampled deformation: {max_sample_error:.6f} heights")
    return {"max_sample_position_error_in_heights": max_sample_error,
            "sample_count": len(before["sample_reference"]["positions"]), "pose_count": len(imported)}
