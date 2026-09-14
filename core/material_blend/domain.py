from __future__ import annotations
import math
from dataclasses import dataclass
from typing import TypeAlias
Color4: TypeAlias = tuple[float, float, float, float]
MIN_SCORE = 1e-12
MIN_WEIGHT = 1e-12

def clamp01(value: float) -> float:
    value = float(value)
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value

def _is_finite(value: float) -> bool:
    return math.isfinite(float(value))

def _validate_finite(*, name: str, value: float) -> float:
    value = float(value)
    if not _is_finite(value):
        raise ValueError(f'{name} must be finite.')
    return value

def _validate_non_negative(*, name: str, value: float) -> float:
    value = _validate_finite(name=name, value=value)
    if value < 0.0:
        raise ValueError(f'{name} must be >= 0.')
    return value

def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """
    Hermite smoothstep in [0, 1].

    Returns:
        0 when x <= edge0
        1 when x >= edge1
        smooth interpolation in-between
    """
    edge0 = _validate_finite(name='edge0', value=edge0)
    edge1 = _validate_finite(name='edge1', value=edge1)
    x = _validate_finite(name='x', value=x)
    if edge1 < edge0:
        raise ValueError('edge1 must be >= edge0.')
    if edge1 == edge0:
        return 1.0 if x >= edge1 else 0.0
    t = clamp01((x - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)

@dataclass(frozen=True)
class MaterialBlendConfig:
    """
    V1.2 blend configuration.

    min_facing:
        Minimum facing before a view starts to contribute.
        Below this value the candidate is considered too
        grazing and gets rejected.

    facing_power:
        Strength applied to the smooth facing confidence
        when converting it to a score.

    relative_score_cutoff:
        Any candidate whose score is below:
            best_score * relative_score_cutoff
        gets rejected.

    max_contributors:
        Maximum number of candidates retained after ranking.

    weight_power:
        Sharpening exponent applied to the retained scores
        before normalization.

        > 1.0 makes the best views dominate more strongly.
    """
    min_facing: float = 0.1
    facing_power: float = 2.0
    relative_score_cutoff: float = 0.2
    max_contributors: int = 3
    weight_power: float = 1.5

    def validate(self) -> None:
        min_facing = _validate_finite(name='min_facing', value=self.min_facing)
        if min_facing < 0.0 or min_facing > 1.0:
            raise ValueError('min_facing must be in [0, 1].')
        facing_power = _validate_finite(name='facing_power', value=self.facing_power)
        if facing_power < 0.0:
            raise ValueError('facing_power must be >= 0.')
        relative_score_cutoff = _validate_finite(name='relative_score_cutoff', value=self.relative_score_cutoff)
        if relative_score_cutoff < 0.0 or relative_score_cutoff > 1.0:
            raise ValueError('relative_score_cutoff must be in [0, 1].')
        if not isinstance(self.max_contributors, int) or self.max_contributors <= 0:
            raise ValueError('max_contributors must be an integer > 0.')
        weight_power = _validate_finite(name='weight_power', value=self.weight_power)
        if weight_power <= 0.0:
            raise ValueError('weight_power must be > 0.')

@dataclass(frozen=True)
class MaterialColorCandidate:
    """
    One candidate view sample.

    base_weight is expected to already include the parts
    independent from the V1.2 selection strategy, for
    example:
        view.weight * alpha

    facing is the directional alignment in [0, 1] for the
    main front-facing pass, or potentially [-1, 1] before
    absolute conversion when fallback mode is used.
    """
    red: float
    green: float
    blue: float
    alpha: float
    base_weight: float
    facing: float
    source_name: str = ''

    def validate(self) -> None:
        for name, value in (('red', self.red), ('green', self.green), ('blue', self.blue), ('alpha', self.alpha), ('base_weight', self.base_weight), ('facing', self.facing)):
            _validate_finite(name=name, value=value)
        if self.base_weight < 0.0:
            raise ValueError('base_weight must be >= 0.')

    @property
    def color(self) -> Color4:
        return (clamp01(self.red), clamp01(self.green), clamp01(self.blue), clamp01(self.alpha))

@dataclass(frozen=True)
class ScoredMaterialCandidate:
    candidate: MaterialColorCandidate
    facing_value: float
    facing_confidence: float
    score: float
    relative_to_best: float
    sharpened_weight: float
    normalized_weight: float

@dataclass(frozen=True)
class MaterialBlendResult:
    """
    Result of one V1.2 selection + blend decision.
    """
    color: Color4 | None
    scored_candidates: tuple[ScoredMaterialCandidate, ...]
    input_candidate_count: int
    eligible_candidate_count: int
    grazing_rejected_count: int
    relative_rejected_count: int
    top_k_rejected_count: int
    selected_count: int
    used_absolute_facing: bool

    @property
    def has_selection(self) -> bool:
        return self.color is not None and self.selected_count > 0

def facing_confidence(facing: float, *, min_facing: float) -> float:
    """
    Convert raw facing to a smooth confidence in [0, 1].
    """
    facing = clamp01(_validate_finite(name='facing', value=facing))
    min_facing = _validate_finite(name='min_facing', value=min_facing)
    if min_facing < 0.0 or min_facing > 1.0:
        raise ValueError('min_facing must be in [0, 1].')
    return smoothstep(min_facing, 1.0, facing)

def candidate_score(candidate: MaterialColorCandidate, config: MaterialBlendConfig, *, use_absolute_facing: bool=False) -> tuple[float, float, float]:
    """
    Return:
        (
            facing_value,
            facing_confidence,
            score,
        )
    """
    candidate.validate()
    config.validate()
    raw_facing = _validate_finite(name='candidate.facing', value=candidate.facing)
    facing_value = abs(raw_facing) if use_absolute_facing else raw_facing
    if facing_value <= 0.0:
        return (0.0, 0.0, 0.0)
    facing_value = clamp01(facing_value)
    confidence = facing_confidence(facing_value, min_facing=config.min_facing)
    if confidence <= 0.0:
        return (facing_value, 0.0, 0.0)
    score = max(0.0, candidate.base_weight) * confidence ** config.facing_power
    if score <= MIN_SCORE:
        return (facing_value, confidence, 0.0)
    return (facing_value, confidence, score)
