"""Geometry benchmark metrics shared by Blender CI and offline tests."""

from __future__ import annotations

from core.image_mask import BinaryMask


def mask_iou(reference: BinaryMask, candidate: BinaryMask) -> float:
    """Return silhouette IoU; an empty pair is never a successful match."""
    if (reference.width, reference.height) != (candidate.width, candidate.height):
        raise ValueError("Reference and candidate masks have different dimensions")
    intersection = sum(a != 0 and b != 0 for a, b in zip(reference.values, candidate.values))
    union = sum(a != 0 or b != 0 for a, b in zip(reference.values, candidate.values))
    return intersection / union if union else 0.0


def score_silhouettes(reference_views: list, candidate_views: list) -> dict:
    """Score all expected views, including missing/empty views as zero."""
    reference = {view.name: view for view in reference_views}
    candidate = {view.name: view for view in candidate_views}
    if not reference or set(reference) != set(candidate):
        raise ValueError("Reference and candidate view names must match and be nonempty")
    per_view = {}
    valid_input_views = 0
    for name, view in reference.items():
        if view.valid and view.mask.occupied_count:
            valid_input_views += 1
            other = candidate[name]
            per_view[name] = mask_iou(view.mask, other.mask) if other.valid else 0.0
        else:
            per_view[name] = 0.0
    return {
        "mean_iou": sum(per_view.values()) / len(per_view),
        "valid_input_views": valid_input_views,
        "total_views": len(per_view),
        "per_view_iou": per_view,
    }
