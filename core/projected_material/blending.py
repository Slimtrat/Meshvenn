from __future__ import annotations
from dataclasses import replace
from ..material_blend import MaterialBlendConfig, MaterialColorCandidate, blend_candidates, choose_best_candidate
from ..material_visibility import MeshVisibilityTester
from ..projection_math import clamp01, normalize3
from .constants import DEFAULT_FALLBACK_COLOR, FALLBACK_FACING_FLOOR
from .models import ProjectedColorResult, ProjectedMaterialView
from .sampling import _collect_candidates

def _resolve_blend_config(blend_config: MaterialBlendConfig | None, *, facing_power: float) -> MaterialBlendConfig:
    """
    Preserve the historical facing_power argument.

    If an explicit V1.2 MaterialBlendConfig is supplied,
    that config owns facing_power as well.
    """
    if blend_config is None:
        resolved = MaterialBlendConfig(facing_power=float(facing_power))
    else:
        resolved = blend_config
    resolved.validate()
    return resolved

def _opaque_color(color: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """
    Projected material remains opaque.

    Source alpha is a confidence/input mask signal, not an
    output transparency channel.
    """
    return (clamp01(color[0]), clamp01(color[1]), clamp01(color[2]), 1.0)

def _fallback_candidates(candidates: tuple[MaterialColorCandidate, ...]) -> list[MaterialColorCandidate]:
    """
    Prepare candidates for the V1-compatible safety fallback.

    Absolute alignment is used and a small floor prevents
    perfectly perpendicular candidates from becoming
    impossible to select.

    This approximates V1.1's historical:

        max(
            0.05,
            abs(facing) ** power
        )

    while keeping actual ranking inside material_blend.py.
    """
    result: list[MaterialColorCandidate] = []
    for candidate in candidates:
        result.append(replace(candidate, facing=max(FALLBACK_FACING_FLOOR, abs(candidate.facing))))
    return result

def _blend_projected_color_detailed(position: tuple[float, float, float], normal: tuple[float, float, float], views: list[ProjectedMaterialView], *, width: int, depth: int, height: int, voxel_size: float=1.0, center_xy: bool=True, facing_power: float=2.0, fallback_color: tuple[float, float, float, float]=DEFAULT_FALLBACK_COLOR, allow_backface_fallback: bool=True, visibility_tester: MeshVisibilityTester | None=None, blend_config: MaterialBlendConfig | None=None) -> ProjectedColorResult:
    """
    V1.2 material projection for one surface point.

    Pipeline:

        source projection
              ↓
        mask / alpha / weight
              ↓
        visibility V1.1
              ↓
        front-facing candidates
              ↓
        MaterialBlendConfig
              ↓
        grazing cutoff
              ↓
        relative score cutoff
              ↓
        top-K
              ↓
        weight sharpening
              ↓
        normalized blend

    If the main pass cannot select anything, an optional
    single-view fallback is attempted using absolute facing.

    Diagnostic pruning counters always describe the main
    adaptive V1.2 pass. The fallback is a recovery path and
    must not overwrite the reason the primary pass failed.
    """
    resolved_config = _resolve_blend_config(blend_config, facing_power=facing_power)
    if not views:
        return ProjectedColorResult(color=fallback_color, used_fallback=True, total_samples=0, candidate_samples=0, source_rejected_samples=0, visible_samples=0, occluded_samples=0, front_facing_samples=0, backface_samples=0, grazing_rejected_samples=0, relative_rejected_samples=0, top_k_rejected_samples=0, selected_samples=0)
    normalized_normal = normalize3(normal)
    collection = _collect_candidates(position, normalized_normal, views, width=width, depth=depth, height=height, voxel_size=voxel_size, center_xy=center_xy, visibility_tester=visibility_tester)
    front_candidates = [candidate for candidate in collection.candidates if candidate.facing > 0.0]
    front_facing_samples = len(front_candidates)
    backface_samples = collection.visible_samples - front_facing_samples
    main_result = blend_candidates(front_candidates, resolved_config, use_absolute_facing=False)
    if main_result.has_selection and main_result.color is not None:
        return ProjectedColorResult(color=_opaque_color(main_result.color), used_fallback=False, total_samples=collection.total_samples, candidate_samples=collection.candidate_samples, source_rejected_samples=collection.source_rejected_samples, visible_samples=collection.visible_samples, occluded_samples=collection.occluded_samples, front_facing_samples=front_facing_samples, backface_samples=backface_samples, grazing_rejected_samples=main_result.grazing_rejected_count, relative_rejected_samples=main_result.relative_rejected_count, top_k_rejected_samples=main_result.top_k_rejected_count, selected_samples=main_result.selected_count)
    if allow_backface_fallback and collection.candidates:
        fallback_config = replace(resolved_config, min_facing=0.0, relative_score_cutoff=0.0)
        fallback_result = choose_best_candidate(_fallback_candidates(collection.candidates), fallback_config, use_absolute_facing=False)
        if fallback_result.has_selection and fallback_result.color is not None:
            return ProjectedColorResult(color=_opaque_color(fallback_result.color), used_fallback=True, total_samples=collection.total_samples, candidate_samples=collection.candidate_samples, source_rejected_samples=collection.source_rejected_samples, visible_samples=collection.visible_samples, occluded_samples=collection.occluded_samples, front_facing_samples=front_facing_samples, backface_samples=backface_samples, grazing_rejected_samples=main_result.grazing_rejected_count, relative_rejected_samples=main_result.relative_rejected_count, top_k_rejected_samples=main_result.top_k_rejected_count, selected_samples=fallback_result.selected_count)
    return ProjectedColorResult(color=fallback_color, used_fallback=True, total_samples=collection.total_samples, candidate_samples=collection.candidate_samples, source_rejected_samples=collection.source_rejected_samples, visible_samples=collection.visible_samples, occluded_samples=collection.occluded_samples, front_facing_samples=front_facing_samples, backface_samples=backface_samples, grazing_rejected_samples=main_result.grazing_rejected_count, relative_rejected_samples=main_result.relative_rejected_count, top_k_rejected_samples=main_result.top_k_rejected_count, selected_samples=0)

def blend_projected_color(position: tuple[float, float, float], normal: tuple[float, float, float], views: list[ProjectedMaterialView], *, width: int, depth: int, height: int, voxel_size: float=1.0, center_xy: bool=True, facing_power: float=2.0, fallback_color: tuple[float, float, float, float]=DEFAULT_FALLBACK_COLOR, allow_backface_fallback: bool=True, visibility_tester: MeshVisibilityTester | None=None, blend_config: MaterialBlendConfig | None=None) -> tuple[tuple[float, float, float, float], int, int, bool]:
    """
    Compatibility wrapper.

    Existing callers still receive:

        (
            RGBA,
            accepted_sample_count,
            rejected_sample_count,
            used_fallback,
        )

    V1.2 semantics:

        accepted_sample_count
            = number of samples actually contributing to
              the final color;

        rejected_sample_count
            = every view which did not contribute.
    """
    result = _blend_projected_color_detailed(position, normal, views, width=width, depth=depth, height=height, voxel_size=voxel_size, center_xy=center_xy, facing_power=facing_power, fallback_color=fallback_color, allow_backface_fallback=allow_backface_fallback, visibility_tester=visibility_tester, blend_config=blend_config)
    return (result.color, result.accepted_samples, result.rejected_samples, result.used_fallback)
