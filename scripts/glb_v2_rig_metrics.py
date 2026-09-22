"""Pure measurements for the GLB-backed Canonical Rig V1 benchmark."""

from __future__ import annotations

import math


# Explicit correspondence between RiggedFigure's source joint heads and the
# semantic heads produced by Canonical Biped V1. Nonmatching extra joints are
# intentionally excluded rather than silently treated as a match.
RIGGED_FIGURE_LANDMARKS = {
    "pelvis": "torso_joint_1",
    "spine": "torso_joint_2",
    "chest": "torso_joint_3",
    "neck": "neck_joint_1",
    "head": "neck_joint_2",
    **{f"{target}.{side}": f"{source}_{side}_{index}" for side in ("L", "R")
       for target, source, index in (
           ("upper_arm", "arm_joint", 1), ("forearm", "arm_joint", 2),
           ("hand", "arm_joint", 3), ("thigh", "leg_joint", 1),
           ("shin", "leg_joint", 2), ("foot", "leg_joint", 3),
       )},
}


def landmark_summary(reference: dict, generated: dict, model_height: float) -> dict:
    if not math.isfinite(model_height) or model_height <= 0:
        raise ValueError("model_height must be positive and finite")
    errors = {}
    for target_name, reference_name in RIGGED_FIGURE_LANDMARKS.items():
        if reference_name not in reference or target_name not in generated:
            raise ValueError(f"Missing corresponding rig landmark: {reference_name} / {target_name}")
        source = tuple(float(value) for value in reference[reference_name])
        candidate = tuple(float(value) for value in generated[target_name])
        if len(source) != 3 or len(candidate) != 3 or any(
            not math.isfinite(value) for value in source + candidate
        ):
            raise ValueError(f"Invalid rig landmark: {target_name}")
        errors[target_name] = math.dist(source, candidate) / model_height
    ordered = sorted(errors.values())
    return {
        "landmark_count": len(errors),
        "mean_error_in_heights": sum(ordered) / len(ordered),
        "max_error_in_heights": ordered[-1],
        "per_landmark_error_in_heights": errors,
    }


def skin_weight_summary(weight_rows: list[list[float]]) -> dict:
    if not weight_rows:
        raise ValueError("No mesh vertices to assess")
    unweighted = 0
    max_influences = 0
    max_normalization_error = 0.0
    for row in weight_rows:
        raw_weights = [float(weight) for weight in row]
        if any(not math.isfinite(weight) or weight < 0 for weight in raw_weights):
            raise ValueError("Skin weights must be finite and nonnegative")
        weights = [weight for weight in raw_weights if weight > 1e-8]
        if not weights:
            unweighted += 1
            continue
        max_influences = max(max_influences, len(weights))
        max_normalization_error = max(max_normalization_error, abs(sum(weights) - 1.0))
    return {
        "vertex_count": len(weight_rows),
        "weighted_fraction": (len(weight_rows) - unweighted) / len(weight_rows),
        "unweighted_vertices": unweighted,
        "max_influences_per_vertex": max_influences,
        "max_weight_sum_error": max_normalization_error,
    }
