"""Deterministic, envelope-guided Canonical Biped V2 fitting.

V1 scales every lateral landmark from the complete mesh width. That makes the
skeleton depend on arm pose: an A- or T-pose widens the bounds and pushes the
shoulders and hips away from the body. V2 uses height-relative torso priors,
tracks each leg from lower-body vertex bands, and derives each arm chain from
its own lateral envelope and observed A/T-pose height.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

from .canonical_rig import BoneSpec, MeshBounds, bounds_from_vertices

Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class CanonicalFitV2Report:
    vertex_count: int
    left_arm_samples: int
    right_arm_samples: int
    left_arm_extent_in_heights: float
    right_arm_extent_in_heights: float
    arm_envelope_height: float
    arm_pose: str
    left_leg_center_in_heights: float
    right_leg_center_in_heights: float
    confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "algorithm": "height-relative-envelope-v2",
            "vertex_count": self.vertex_count,
            "left_arm_samples": self.left_arm_samples,
            "right_arm_samples": self.right_arm_samples,
            "left_arm_extent_in_heights": self.left_arm_extent_in_heights,
            "right_arm_extent_in_heights": self.right_arm_extent_in_heights,
            "arm_envelope_height": self.arm_envelope_height,
            "arm_pose": self.arm_pose,
            "left_leg_center_in_heights": self.left_leg_center_in_heights,
            "right_leg_center_in_heights": self.right_leg_center_in_heights,
            "confidence": self.confidence,
        }


def _finite_points(vertices: Iterable[Sequence[float]]) -> tuple[Point3, ...]:
    points = tuple(tuple(float(value) for value in vertex) for vertex in vertices)
    if not points:
        raise ValueError("Cannot fit Canonical Biped V2 to an empty mesh.")
    if any(len(point) != 3 or any(not math.isfinite(value) for value in point) for point in points):
        raise ValueError("Canonical Biped V2 vertices must contain three finite coordinates.")
    return points


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise ValueError("Cannot measure an empty envelope.")
    ordered = sorted(values)
    rank = fraction * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _median_or(values: Sequence[float], fallback: float) -> float:
    return float(statistics.median(values)) if values else fallback


def _side_leg_center(
    points: Sequence[Point3], bounds: MeshBounds, side: int, z_low: float, z_high: float
) -> float:
    height = bounds.height
    center = bounds.center_x
    candidates = [
        side * (point[0] - center) / height
        for point in points
        if z_low <= (point[2] - bounds.minimum[2]) / height <= z_high
        and 0.01 < side * (point[0] - center) / height < 0.18
    ]
    return _median_or(candidates, 0.052)


def fit_canonical_biped_v2(
    vertices: Iterable[Sequence[float]],
) -> tuple[tuple[BoneSpec, ...], CanonicalFitV2Report]:
    """Fit the stable 18-bone hierarchy from deterministic mesh envelopes."""
    points = _finite_points(vertices)
    bounds = bounds_from_vertices(points)
    height = bounds.height
    floor = bounds.minimum[2]
    center_x = bounds.center_x
    torso_y = _median_or([
        point[1]
        for point in points
        if 0.35 <= (point[2] - floor) / height <= 0.80
        and abs(point[0] - center_x) <= 0.12 * height
    ], bounds.center_y)

    side_extents: dict[int, float] = {}
    side_samples: dict[int, list[Point3]] = {}
    for side in (1, -1):
        samples = [
            point for point in points
            if side * (point[0] - center_x) > 0.22 * height
            and 0.35 <= (point[2] - floor) / height <= 0.82
        ]
        side_samples[side] = samples
        distances = [side * (point[0] - center_x) / height for point in samples]
        fallback = min(0.40, max(0.28, bounds.width / (2.0 * height)))
        side_extents[side] = _percentile(distances, 0.98) if distances else fallback

    arm_z_samples = [
        (point[2] - floor) / height
        for samples in side_samples.values() for point in samples
    ]
    arm_envelope_height = _median_or(arm_z_samples, 0.59)
    wrist_z = max(0.54, min(0.76, arm_envelope_height + 0.02))
    shoulder_z = 0.741
    elbow_z = shoulder_z + 0.52 * (wrist_z - shoulder_z)
    arm_pose = "t-pose" if wrist_z >= 0.70 else "a-pose"

    leg_centers = {
        side: _side_leg_center(points, bounds, side, 0.08, 0.44)
        for side in (1, -1)
    }

    def point(x_heights: float, z_fraction: float, y: float = torso_y) -> Point3:
        return (center_x + x_heights * height, y, floor + z_fraction * height)

    root = point(0.0, 0.02)
    pelvis = point(0.0, 0.473)
    spine = point(0.0, 0.591)
    chest = point(0.0, shoulder_z)
    neck = point(0.0, 0.777)
    head_base = point(0.0, 0.823)
    specs = [
        BoneSpec("root", None, root, pelvis, False),
        BoneSpec("pelvis", "root", pelvis, spine),
        BoneSpec("spine", "pelvis", spine, chest),
        BoneSpec("chest", "spine", chest, neck),
        BoneSpec("neck", "chest", neck, head_base),
        BoneSpec("head", "neck", head_base, point(0.0, 0.97)),
    ]
    for side_name, side in (("L", 1), ("R", -1)):
        extent = side_extents[side]
        shoulder_x = side * min(0.065, 0.15 * extent)
        elbow_x = side * min(0.225, 0.52 * extent)
        wrist_x = side * min(0.325, 0.76 * extent)
        finger_x = side * min(0.40, 0.94 * extent)
        hip_x = side * min(0.075, leg_centers[side] * 0.92)
        knee_x = side * min(0.080, leg_centers[side])
        ankle_x = side * min(0.080, leg_centers[side] * 1.02)
        shoulder = point(shoulder_x, shoulder_z)
        elbow = point(elbow_x, elbow_z)
        wrist = point(wrist_x, wrist_z)
        finger = point(finger_x, max(0.45, wrist_z - 0.045))
        hip = point(hip_x, 0.424)
        knee = point(knee_x, 0.244)
        ankle = point(ankle_x, 0.059)
        toe = point(ankle_x, 0.015, bounds.minimum[1])
        specs.extend((
            BoneSpec(f"upper_arm.{side_name}", "chest", shoulder, elbow),
            BoneSpec(f"forearm.{side_name}", f"upper_arm.{side_name}", elbow, wrist),
            BoneSpec(f"hand.{side_name}", f"forearm.{side_name}", wrist, finger),
            BoneSpec(f"thigh.{side_name}", "pelvis", hip, knee),
            BoneSpec(f"shin.{side_name}", f"thigh.{side_name}", knee, ankle),
            BoneSpec(f"foot.{side_name}", f"shin.{side_name}", ankle, toe),
        ))

    sample_confidence = min(1.0, min(len(side_samples[1]), len(side_samples[-1])) / 24.0)
    balance = min(side_extents.values()) / max(side_extents.values())
    confidence = max(0.0, min(1.0, sample_confidence * balance))
    report = CanonicalFitV2Report(
        vertex_count=len(points),
        left_arm_samples=len(side_samples[1]),
        right_arm_samples=len(side_samples[-1]),
        left_arm_extent_in_heights=side_extents[1],
        right_arm_extent_in_heights=side_extents[-1],
        arm_envelope_height=arm_envelope_height,
        arm_pose=arm_pose,
        left_leg_center_in_heights=leg_centers[1],
        right_leg_center_in_heights=leg_centers[-1],
        confidence=confidence,
    )
    return tuple(specs), report
