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
from .rig_lower_body import fit_lower_body

Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class CanonicalFitV2Report:
    vertex_count: int
    unique_position_count: int
    left_arm_samples: int
    right_arm_samples: int
    left_arm_extent_in_heights: float
    right_arm_extent_in_heights: float
    left_arm_thickness_in_heights: float
    right_arm_thickness_in_heights: float
    arm_envelope_height: float
    arm_pose: str
    left_leg_center_in_heights: float
    right_leg_center_in_heights: float
    confidence: float
    lower_body: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "algorithm": "height-relative-local-envelope-v2",
            "vertex_count": self.vertex_count,
            "unique_position_count": self.unique_position_count,
            "left_arm_samples": self.left_arm_samples,
            "right_arm_samples": self.right_arm_samples,
            "left_arm_extent_in_heights": self.left_arm_extent_in_heights,
            "right_arm_extent_in_heights": self.right_arm_extent_in_heights,
            "left_arm_thickness_in_heights": self.left_arm_thickness_in_heights,
            "right_arm_thickness_in_heights": self.right_arm_thickness_in_heights,
            "depth_policy": "trimmed-local-surface-envelope",
            "body_height_policy": "observed-leg-cues with explicit hip/axial priors; not inferred anatomy",
            "lower_body": self.lower_body,
            "arm_envelope_height": self.arm_envelope_height,
            "arm_pose": self.arm_pose,
            "left_leg_center_in_heights": self.left_leg_center_in_heights,
            "right_leg_center_in_heights": self.right_leg_center_in_heights,
            "confidence": self.confidence,
            "confidence_scope": "arm-envelope-coverage; lower_body reports separate leg evidence",
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


def _envelope_center(values: Sequence[float], fallback: float) -> float:
    # Surface vertex density is not volume density: the median can sit on the
    # front/back skin. Trim isolated extrema and center the observed envelope.
    if len(values) < 4:
        return fallback
    return (_percentile(values, 0.05) + _percentile(values, 0.95)) * 0.5


def _arm_height_line(samples: Sequence[Point3], center: float, floor: float,
                     height: float, side: int, extent: float, fallback: float):
    centers = []
    thickness = []
    lower = 0.22
    for index in range(5):
        low = lower + (extent - lower) * index / 5
        high = lower + (extent - lower) * (index + 1) / 5
        band = [(side * (x - center) / height, (z - floor) / height)
                for x, _, z in samples if low <= side * (x - center) / height < high]
        if len(band) >= 4:
            thickness.append(_percentile([z for _, z in band], 0.95)
                             - _percentile([z for _, z in band], 0.05))
            centers.append((statistics.median([x for x, _ in band]),
                            _envelope_center([z for _, z in band], fallback)))
    if len(centers) < 2:
        return (lambda _: fallback), max(thickness, default=0.0)
    origin_x = statistics.mean(x for x, _ in centers)
    origin_z = statistics.mean(z for _, z in centers)
    denominator = sum((x - origin_x) ** 2 for x, _ in centers)
    slope = (sum((x - origin_x) * (z - origin_z) for x, z in centers) / denominator
             if denominator > 1.0e-12 else 0.0)
    slope = max(-1.0, min(0.25, slope))
    return (lambda x: max(0.40, min(0.86, origin_z + slope * (x - origin_x)))), max(thickness, default=0.0)


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
    *, triangles: Iterable[Sequence[int]] | None = None,
) -> tuple[tuple[BoneSpec, ...], CanonicalFitV2Report]:
    """Fit the stable 18-bone hierarchy from deterministic mesh envelopes."""
    raw_points = _finite_points(vertices)
    # UV/material seams can duplicate positions when glTF is exported. They
    # must not change the fitted anatomy or inflate observation confidence.
    points = tuple(sorted(set(raw_points)))
    bounds = bounds_from_vertices(points)
    height = bounds.height
    floor = bounds.minimum[2]
    center_x = bounds.center_x
    torso_y = _envelope_center([
        point[1]
        for point in points
        if 0.35 <= (point[2] - floor) / height <= 0.80
        and abs(point[0] - center_x) <= 0.12 * height
    ], bounds.center_y)

    def depth_at(x_fraction: float, z_fraction: float, fallback: float = torso_y) -> float:
        return _envelope_center([
            y for x, y, z in points
            if abs((x - center_x) / height - x_fraction) <= 0.045
            and abs((z - floor) / height - z_fraction) <= 0.055
        ], fallback)

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
    shoulder_z = 0.741
    arm_pose = "t-pose" if arm_envelope_height >= 0.68 else "a-pose"

    leg_centers = {
        side: _side_leg_center(points, bounds, side, 0.08, 0.44)
        for side in (1, -1)
    }
    lower_body = fit_lower_body(raw_points, triangles, bounds)
    measured_hips = [leg.hip[2] for leg in (lower_body.left, lower_body.right) if leg.hip is not None]
    pelvis_z = max(0.473, (sum(measured_hips) / len(measured_hips) - floor) / height) if measured_hips else 0.473
    lower_body.evidence["pelvis_height_in_heights"] = pelvis_z
    lower_body.evidence["pelvis_policy"] = "canonical anchor, raised only to bilateral observed-link hip prior"

    def point(x_heights: float, z_fraction: float, y: float | None = None) -> Point3:
        return (center_x + x_heights * height,
                depth_at(x_heights, z_fraction) if y is None else y,
                floor + z_fraction * height)

    root = point(0.0, 0.02)
    pelvis = point(0.0, pelvis_z)
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
    arm_thickness = {}
    for side_name, side in (("L", 1), ("R", -1)):
        extent = side_extents[side]
        arm_line, arm_thickness[side] = _arm_height_line(
            side_samples[side], center_x, floor, height, side, extent, arm_envelope_height
        )
        # Long T-pose arms must not be capped at proportions of the first A-pose
        # fixture. The measured span and local trajectory define each chain.
        side_pose = "t-pose" if arm_line(0.78 * extent) >= 0.70 else "a-pose"
        shoulder_x = side * (0.20 if side_pose == "t-pose" else 0.15) * extent
        elbow_x = side * 0.52 * extent
        wrist_x = side * 0.78 * extent
        finger_x = side * 0.94 * extent
        hip_x = side * min(0.075, leg_centers[side] * 0.92)
        knee_x = side * min(0.080, leg_centers[side])
        ankle_x = side * min(0.080, leg_centers[side] * 1.02)
        side_shoulder_z = arm_line(abs(shoulder_x)) if side_pose == "t-pose" else shoulder_z
        side_wrist_z = arm_line(abs(wrist_x))
        side_elbow_z = (arm_line(abs(elbow_x)) if side_pose == "t-pose" else
                        side_shoulder_z + (0.52 - 0.15) / (0.78 - 0.15) * (side_wrist_z - side_shoulder_z))
        shoulder = point(shoulder_x, side_shoulder_z)
        elbow = point(elbow_x, side_elbow_z)
        wrist = point(wrist_x, arm_line(abs(wrist_x)))
        finger = point(finger_x, arm_line(abs(finger_x)))
        hip = point(hip_x, 0.424)
        knee = point(knee_x, 0.244)
        ankle = point(ankle_x, 0.059, depth_at(ankle_x, 0.13))
        toe = point(ankle_x, 0.015, bounds.minimum[1])
        observed = lower_body.left if side == 1 else lower_body.right
        applied = {}

        def regularized(name, measurement, prior):
            # Surface cues are not exact joint centers. Below one percent of
            # height, retain the stable prior instead of chasing slice noise.
            if measurement is None:
                applied[name] = "canonical-fallback"
                return prior
            if math.dist(measurement, prior) <= .01 * height:
                applied[name] = "canonical-within-observation-resolution"
                return prior
            applied[name] = "surface-cue" if name != "hip" else "observed-link-length-prior"
            return measurement

        hip = regularized("hip", observed.hip, hip)
        knee = regularized("knee", observed.knee, knee)
        ankle = regularized("ankle", observed.ankle, ankle)
        lower_body.evidence.setdefault("applied_anchors", {})[side_name] = applied
        if observed.toe_y is not None:
            toe = (ankle[0], observed.toe_y, floor + min(.015 * height, .35 * (ankle[2] - floor)))
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
        vertex_count=len(raw_points),
        unique_position_count=len(points),
        left_arm_samples=len(side_samples[1]),
        right_arm_samples=len(side_samples[-1]),
        left_arm_extent_in_heights=side_extents[1],
        right_arm_extent_in_heights=side_extents[-1],
        left_arm_thickness_in_heights=arm_thickness[1],
        right_arm_thickness_in_heights=arm_thickness[-1],
        arm_envelope_height=arm_envelope_height,
        arm_pose=arm_pose,
        left_leg_center_in_heights=leg_centers[1],
        right_leg_center_in_heights=leg_centers[-1],
        confidence=confidence,
        lower_body=lower_body.evidence,
    )
    return tuple(specs), report
