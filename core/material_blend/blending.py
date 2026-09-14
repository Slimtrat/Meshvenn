from __future__ import annotations
from .domain import Color4, MIN_SCORE, MIN_WEIGHT, clamp01
from .domain import MaterialBlendConfig, MaterialBlendResult, MaterialColorCandidate, ScoredMaterialCandidate
from .domain import candidate_score

def blend_candidates(candidates: list[MaterialColorCandidate], config: MaterialBlendConfig, *, use_absolute_facing: bool=False, max_contributors: int | None=None) -> MaterialBlendResult:
    """
    Main V1.2 selection pipeline.

    Steps:
        1. score all candidates
        2. reject grazing / near-zero candidates
        3. keep candidates close enough to best score
        4. keep top-K
        5. sharpen retained weights
        6. blend RGB

    If nothing survives, color is None.
    """
    config.validate()
    if max_contributors is None:
        effective_max_contributors = config.max_contributors
    else:
        if not isinstance(max_contributors, int) or max_contributors <= 0:
            raise ValueError('max_contributors override must be an integer > 0.')
        effective_max_contributors = max_contributors
    input_candidate_count = len(candidates)
    provisional: list[tuple[MaterialColorCandidate, float, float, float]] = []
    grazing_rejected_count = 0
    for candidate in candidates:
        facing_value, confidence, score = candidate_score(candidate, config, use_absolute_facing=use_absolute_facing)
        if score <= MIN_SCORE:
            grazing_rejected_count += 1
            continue
        provisional.append((candidate, facing_value, confidence, score))
    eligible_candidate_count = len(provisional)
    if not provisional:
        return MaterialBlendResult(color=None, scored_candidates=(), input_candidate_count=input_candidate_count, eligible_candidate_count=0, grazing_rejected_count=grazing_rejected_count, relative_rejected_count=0, top_k_rejected_count=0, selected_count=0, used_absolute_facing=use_absolute_facing)
    best_score = max((score for _candidate, _facing_value, _confidence, score in provisional))
    if best_score <= MIN_SCORE:
        return MaterialBlendResult(color=None, scored_candidates=(), input_candidate_count=input_candidate_count, eligible_candidate_count=eligible_candidate_count, grazing_rejected_count=grazing_rejected_count, relative_rejected_count=0, top_k_rejected_count=0, selected_count=0, used_absolute_facing=use_absolute_facing)
    relative_threshold = best_score * config.relative_score_cutoff
    relative_filtered: list[tuple[MaterialColorCandidate, float, float, float, float]] = []
    relative_rejected_count = 0
    for candidate, facing_value, confidence, score in provisional:
        relative_to_best = score / best_score
        if score + MIN_SCORE < relative_threshold:
            relative_rejected_count += 1
            continue
        relative_filtered.append((candidate, facing_value, confidence, score, relative_to_best))
    if not relative_filtered:
        return MaterialBlendResult(color=None, scored_candidates=(), input_candidate_count=input_candidate_count, eligible_candidate_count=eligible_candidate_count, grazing_rejected_count=grazing_rejected_count, relative_rejected_count=relative_rejected_count, top_k_rejected_count=0, selected_count=0, used_absolute_facing=use_absolute_facing)
    relative_filtered.sort(key=lambda item: (item[3], item[2], item[1], item[0].base_weight), reverse=True)
    selected_raw = relative_filtered[:effective_max_contributors]
    top_k_rejected_count = max(0, len(relative_filtered) - len(selected_raw))
    sharpened_total = 0.0
    sharpened_values: list[float] = []
    for _candidate, _facing_value, _confidence, score, _relative_to_best in selected_raw:
        sharpened = max(score, MIN_WEIGHT) ** config.weight_power
        sharpened_values.append(sharpened)
        sharpened_total += sharpened
    if sharpened_total <= MIN_WEIGHT:
        return MaterialBlendResult(color=None, scored_candidates=(), input_candidate_count=input_candidate_count, eligible_candidate_count=eligible_candidate_count, grazing_rejected_count=grazing_rejected_count, relative_rejected_count=relative_rejected_count, top_k_rejected_count=top_k_rejected_count, selected_count=0, used_absolute_facing=use_absolute_facing)
    scored_candidates: list[ScoredMaterialCandidate] = []
    blended_red = 0.0
    blended_green = 0.0
    blended_blue = 0.0
    blended_alpha = 0.0
    for index, (candidate, facing_value, confidence, score, relative_to_best) in enumerate(selected_raw):
        normalized_weight = sharpened_values[index] / sharpened_total
        scored = ScoredMaterialCandidate(candidate=candidate, facing_value=facing_value, facing_confidence=confidence, score=score, relative_to_best=relative_to_best, sharpened_weight=sharpened_values[index], normalized_weight=normalized_weight)
        scored_candidates.append(scored)
        blended_red += candidate.red * normalized_weight
        blended_green += candidate.green * normalized_weight
        blended_blue += candidate.blue * normalized_weight
        blended_alpha += candidate.alpha * normalized_weight
    color: Color4 = (clamp01(blended_red), clamp01(blended_green), clamp01(blended_blue), clamp01(blended_alpha))
    return MaterialBlendResult(color=color, scored_candidates=tuple(scored_candidates), input_candidate_count=input_candidate_count, eligible_candidate_count=eligible_candidate_count, grazing_rejected_count=grazing_rejected_count, relative_rejected_count=relative_rejected_count, top_k_rejected_count=top_k_rejected_count, selected_count=len(scored_candidates), used_absolute_facing=use_absolute_facing)

def choose_best_candidate(candidates: list[MaterialColorCandidate], config: MaterialBlendConfig, *, use_absolute_facing: bool=False) -> MaterialBlendResult:
    """
    Convenience wrapper for fallback-style selection.

    Equivalent to blend_candidates(..., max_contributors=1).
    """
    return blend_candidates(candidates, config, use_absolute_facing=use_absolute_facing, max_contributors=1)
