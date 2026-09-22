"""Region-aware deterministic fallback skinning for Canonical Biped V1.

This is a spatial prior, not anatomical segmentation. It limits distant bone
influences by chain and side before weighting the remaining bone segments.
The transitions are smooth so shoulders and hips can share their parent chain.
"""

from __future__ import annotations

import math
from typing import Sequence

from .canonical_rig import BoneSpec, MeshBounds


_AXIAL = ("pelvis", "spine", "chest", "neck", "head")
_ARMS = ("upper_arm", "forearm", "hand")
_LEGS = ("thigh", "shin", "foot")
_REQUIRED = frozenset((*_AXIAL, *(f"{name}.{side}" for side in ("L", "R")
                                 for name in (*_ARMS, *_LEGS))))
_RELATIVE_SCORE_FLOOR = 0.001


def _smoothstep(start: float, end: float, value: float) -> float:
    fraction = max(0.0, min(1.0, (value - start) / (end - start)))
    return fraction * fraction * (3.0 - 2.0 * fraction)


def _segment_distance(point: tuple[float, float, float], bone: BoneSpec, scale: float) -> float:
    """Distance in a scale-normalized coordinate frame to avoid power overflow."""

    segment = tuple((tail - head) / scale for head, tail in zip(bone.head, bone.tail))
    offset = tuple((value - head) / scale for value, head in zip(point, bone.head))
    length_squared = sum(value * value for value in segment)
    fraction = max(0.0, min(1.0, sum(a * b for a, b in zip(offset, segment)) / length_squared))
    return math.sqrt(sum((offset[i] - fraction * segment[i]) ** 2 for i in range(3)))


def _region_gates(point: tuple[float, float, float], bounds: MeshBounds) -> dict[str, float]:
    lateral = (point[0] - bounds.center_x) / bounds.width
    outward = abs(lateral)
    height = (point[2] - bounds.minimum[2]) / bounds.height

    # The arm and thigh overlap in height near the waist. Lateral position
    # separates them there, while the axial chain bridges both joints.
    axial = max(0.02, 1.0 - _smoothstep(0.18, 0.38, outward))
    arm = (_smoothstep(0.17, 0.30, outward)
           * _smoothstep(0.37, 0.50, height)
           * (1.0 - _smoothstep(0.87, 0.97, height)))
    leg = ((1.0 - _smoothstep(0.52, 0.60, height))
           * _smoothstep(0.015, 0.09, outward))
    # Wrong-side limbs are excluded beyond a narrow midline transition;
    # axial bones remain available even for exaggerated silhouettes.
    return {
        "axial": axial,
        "arm.L": arm * _smoothstep(-0.035, 0.035, lateral),
        "arm.R": arm * _smoothstep(-0.035, 0.035, -lateral),
        "leg.L": leg * _smoothstep(-0.035, 0.035, lateral),
        "leg.R": leg * _smoothstep(-0.035, 0.035, -lateral),
    }


def _bone_gate(name: str, gates: dict[str, float]) -> float:
    if name in _AXIAL:
        return gates["axial"]
    family, side = name.rsplit(".", 1)
    return gates[("arm" if family in _ARMS else "leg") + "." + side]


def regional_fallback_weights(
    point: Sequence[float],
    bones: Sequence[BoneSpec],
    bounds: MeshBounds,
    *,
    max_influences: int = 4,
) -> dict[str, float]:
    """Return bounded skin weights for a point in a Canonical Biped mesh.

    X is lateral, Z is up, and anatomical left is +X. The model intentionally
    favours the axial chain for ambiguous centerline points; a diagnostic of
    geometric suitability must still accompany a generated rig.
    """

    if not isinstance(bounds, MeshBounds):
        raise TypeError("bounds must be a MeshBounds instance.")
    if not isinstance(max_influences, int) or max_influences < 1:
        raise ValueError("max_influences must be a positive integer.")
    coordinates = tuple(float(value) for value in point)
    if len(coordinates) != 3 or any(not math.isfinite(value) for value in coordinates):
        raise ValueError("point must contain three finite coordinates.")
    dimensions = (bounds.width, bounds.depth, bounds.height)
    if any(not math.isfinite(value) for value in dimensions):
        raise ValueError("bounds dimensions must be finite.")
    tolerance = 1e-6 * max(dimensions)
    if any(value < low - tolerance or value > high + tolerance for value, low, high in
           zip(coordinates, bounds.minimum, bounds.maximum)):
        raise ValueError("point must lie within bounds.")

    deform = {bone.name: bone for bone in bones if bone.deform}
    if len(deform) != sum(bone.deform for bone in bones) or not _REQUIRED.issubset(deform):
        raise ValueError("Canonical Biped V1 requires unique deforming bones in every region.")
    scale = max(dimensions)
    softness = max(0.040 * bounds.height / scale, 0.025 * bounds.width / scale, 1e-8)
    gates = _region_gates(coordinates, bounds)
    scores: list[tuple[float, str]] = []
    for name in sorted(_REQUIRED):
        gate = _bone_gate(name, gates)
        if gate <= 0.0:
            continue
        distance = _segment_distance(coordinates, deform[name], scale)
        score = gate / (distance * distance + softness * softness) ** 1.5
        if not math.isfinite(score) or score <= 0.0:
            raise ValueError("Cannot calculate finite skin weights for this mesh.")
        scores.append((score, name))
    # Axial gating guarantees at least one candidate, including at extreme
    # stylized silhouettes where neither canonical limb prior is plausible.
    scores.sort(key=lambda item: (-item[0], item[1]))
    strongest = scores[0][0]
    selected = [item for item in scores[:max_influences]
                if item[0] >= strongest * _RELATIVE_SCORE_FLOOR]
    total = sum(score for score, _ in selected)
    return {name: score / total for score, name in selected}
