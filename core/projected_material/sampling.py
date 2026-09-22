from __future__ import annotations
import math
from ..image_mask import BinaryMask
from ..material_blend import MaterialColorCandidate
from ..material_visibility import MeshVisibilityTester
from ..projection_math import dot3, project_surface_position
from .constants import MIN_ALPHA, MIN_BASE_WEIGHT
from .models import ProjectedMaterialView, _CandidateCollection

def _sample_mask(mask: BinaryMask, u: float, v: float) -> bool:
    """
    Nearest-neighbour mask sampling.

    Deliberately matches native/src/visual_hull.cpp:

        int(
            u * (width - 1)
            + 0.5
        )
    """
    if u < 0.0 or u > 1.0 or v < 0.0 or (v > 1.0):
        return False
    x = int(u * float(mask.width - 1) + 0.5)
    y = int(v * float(mask.height - 1) + 0.5)
    x = max(0, min(mask.width - 1, x))
    y = max(0, min(mask.height - 1, y))
    return mask.get(x, y)

def _sample_source_view(position: tuple[float, float, float], normal: tuple[float, float, float], view: ProjectedMaterialView, *, width: int, depth: int, height: int, voxel_size: float, center_xy: bool) -> MaterialColorCandidate | None:
    """
    Collect one geometrically plausible source sample.

    IMPORTANT:

    This function intentionally does NOT perform:

        - grazing rejection
        - relative score filtering
        - top-K filtering
        - weight sharpening

    Those decisions belong exclusively to
    material_blend.py.

    Visibility is also handled one level above so it can be
    counted independently.
    """
    projected = project_surface_position(position, transform=view.transform, width=width, depth=depth, height=height, voxel_size=voxel_size, center_xy=center_xy)
    if not projected.inside:
        return None
    if view.mask is not None and (not _sample_mask(view.mask, projected.u, projected.v)):
        return None
    source_u, source_v = view.alignment.source_uv(projected.u, projected.v)
    if not (0.0 <= source_u <= 1.0 and 0.0 <= source_v <= 1.0):
        return None
    red, green, blue, alpha = view.image.sample_bilinear(source_u, source_v)
    if not math.isfinite(alpha) or alpha <= MIN_ALPHA:
        return None
    base_weight = view.weight * alpha
    if not math.isfinite(base_weight) or base_weight <= MIN_BASE_WEIGHT:
        return None
    facing = dot3(normal, view.camera_direction)
    if not math.isfinite(facing):
        return None
    return MaterialColorCandidate(red=float(red), green=float(green), blue=float(blue), alpha=float(alpha), base_weight=float(base_weight), facing=float(facing), source_name=view.name)

def _collect_candidates(position: tuple[float, float, float], normal: tuple[float, float, float], views: list[ProjectedMaterialView], *, width: int, depth: int, height: int, voxel_size: float, center_xy: bool, visibility_tester: MeshVisibilityTester | None) -> _CandidateCollection:
    """
    Build all RGB candidates once.

    Visibility is evaluated BEFORE material blending.

    This means material_blend.py never needs Blender,
    BVHTree, projection transforms or source images.

    For V1.2 we deliberately visibility-test every valid
    projected candidate, including back-facing candidates.

    Benefits:

        - visible_samples and occluded_samples are exact;
        - candidate_samples =
              visible_samples + occluded_samples
          whenever visibility is enabled;
        - fallback does not need to raycast a second time.
    """
    total_samples = len(views)
    candidate_samples = 0
    source_rejected_samples = 0
    visible_samples = 0
    occluded_samples = 0
    candidates: list[MaterialColorCandidate] = []
    for view in views:
        candidate = _sample_source_view(position, normal, view, width=width, depth=depth, height=height, voxel_size=voxel_size, center_xy=center_xy)
        if candidate is None:
            source_rejected_samples += 1
            continue
        candidate_samples += 1
        if visibility_tester is not None:
            visibility = visibility_tester.query(position, view.camera_direction)
            if not visibility.visible:
                occluded_samples += 1
                continue
        visible_samples += 1
        candidates.append(candidate)
    return _CandidateCollection(candidates=tuple(candidates), total_samples=total_samples, candidate_samples=candidate_samples, source_rejected_samples=source_rejected_samples, visible_samples=visible_samples, occluded_samples=occluded_samples)
