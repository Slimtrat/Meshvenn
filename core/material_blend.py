from __future__ import annotations

import math

from dataclasses import dataclass
from typing import TypeAlias


# ---------------------------------------------------------
# Types
# ---------------------------------------------------------

Color4: TypeAlias = tuple[
    float,
    float,
    float,
    float,
]


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

MIN_SCORE = 1e-12
MIN_WEIGHT = 1e-12


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def clamp01(
    value: float,
) -> float:
    value = float(value)

    if value <= 0.0:
        return 0.0

    if value >= 1.0:
        return 1.0

    return value


def _is_finite(
    value: float,
) -> bool:
    return math.isfinite(
        float(value)
    )


def _validate_finite(
    *,
    name: str,
    value: float,
) -> float:
    value = float(value)

    if not _is_finite(
        value
    ):
        raise ValueError(
            f"{name} must be finite."
        )

    return value


def _validate_non_negative(
    *,
    name: str,
    value: float,
) -> float:
    value = _validate_finite(
        name=name,
        value=value,
    )

    if value < 0.0:
        raise ValueError(
            f"{name} must be >= 0."
        )

    return value


def smoothstep(
    edge0: float,
    edge1: float,
    x: float,
) -> float:
    """
    Hermite smoothstep in [0, 1].

    Returns:
        0 when x <= edge0
        1 when x >= edge1
        smooth interpolation in-between
    """

    edge0 = _validate_finite(
        name="edge0",
        value=edge0,
    )

    edge1 = _validate_finite(
        name="edge1",
        value=edge1,
    )

    x = _validate_finite(
        name="x",
        value=x,
    )

    if edge1 < edge0:
        raise ValueError(
            "edge1 must be >= edge0."
        )

    if edge1 == edge0:
        return (
            1.0
            if x >= edge1
            else 0.0
        )

    t = clamp01(
        (x - edge0)
        / (edge1 - edge0)
    )

    return (
        t
        * t
        * (3.0 - 2.0 * t)
    )


# ---------------------------------------------------------
# Config
# ---------------------------------------------------------

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

    min_facing: float = 0.10

    facing_power: float = 2.0

    relative_score_cutoff: float = 0.20

    max_contributors: int = 3

    weight_power: float = 1.5

    def validate(
        self,
    ) -> None:
        min_facing = _validate_finite(
            name="min_facing",
            value=self.min_facing,
        )

        if (
            min_facing < 0.0
            or min_facing > 1.0
        ):
            raise ValueError(
                "min_facing must be in [0, 1]."
            )

        facing_power = _validate_finite(
            name="facing_power",
            value=self.facing_power,
        )

        if facing_power < 0.0:
            raise ValueError(
                "facing_power must be >= 0."
            )

        relative_score_cutoff = _validate_finite(
            name="relative_score_cutoff",
            value=self.relative_score_cutoff,
        )

        if (
            relative_score_cutoff < 0.0
            or relative_score_cutoff > 1.0
        ):
            raise ValueError(
                "relative_score_cutoff must be in [0, 1]."
            )

        if (
            not isinstance(
                self.max_contributors,
                int
            )
            or self.max_contributors <= 0
        ):
            raise ValueError(
                "max_contributors must be an integer > 0."
            )

        weight_power = _validate_finite(
            name="weight_power",
            value=self.weight_power,
        )

        if weight_power <= 0.0:
            raise ValueError(
                "weight_power must be > 0."
            )


# ---------------------------------------------------------
# Candidate
# ---------------------------------------------------------

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

    source_name: str = ""

    def validate(
        self,
    ) -> None:
        for (
            name,
            value,
        ) in (
            ("red", self.red),
            ("green", self.green),
            ("blue", self.blue),
            ("alpha", self.alpha),
            ("base_weight", self.base_weight),
            ("facing", self.facing),
        ):
            _validate_finite(
                name=name,
                value=value,
            )

        if self.base_weight < 0.0:
            raise ValueError(
                "base_weight must be >= 0."
            )

    @property
    def color(
        self,
    ) -> Color4:
        return (
            clamp01(self.red),
            clamp01(self.green),
            clamp01(self.blue),
            clamp01(self.alpha),
        )


# ---------------------------------------------------------
# Scored candidate / result
# ---------------------------------------------------------

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

    scored_candidates: tuple[
        ScoredMaterialCandidate,
        ...
    ]

    input_candidate_count: int

    eligible_candidate_count: int

    grazing_rejected_count: int

    relative_rejected_count: int

    top_k_rejected_count: int

    selected_count: int

    used_absolute_facing: bool

    @property
    def has_selection(
        self,
    ) -> bool:
        return (
            self.color is not None
            and self.selected_count > 0
        )


# ---------------------------------------------------------
# Scoring
# ---------------------------------------------------------

def facing_confidence(
    facing: float,
    *,
    min_facing: float,
) -> float:
    """
    Convert raw facing to a smooth confidence in [0, 1].
    """

    facing = clamp01(
        _validate_finite(
            name="facing",
            value=facing,
        )
    )

    min_facing = _validate_finite(
        name="min_facing",
        value=min_facing,
    )

    if (
        min_facing < 0.0
        or min_facing > 1.0
    ):
        raise ValueError(
            "min_facing must be in [0, 1]."
        )

    return smoothstep(
        min_facing,
        1.0,
        facing,
    )


def candidate_score(
    candidate: MaterialColorCandidate,
    config: MaterialBlendConfig,
    *,
    use_absolute_facing: bool = False,
) -> tuple[
    float,
    float,
    float,
]:
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

    raw_facing = _validate_finite(
        name="candidate.facing",
        value=candidate.facing,
    )

    facing_value = (
        abs(raw_facing)
        if use_absolute_facing
        else raw_facing
    )

    if facing_value <= 0.0:
        return (
            0.0,
            0.0,
            0.0,
        )

    facing_value = clamp01(
        facing_value
    )

    confidence = facing_confidence(
        facing_value,
        min_facing=config.min_facing,
    )

    if confidence <= 0.0:
        return (
            facing_value,
            0.0,
            0.0,
        )

    score = (
        max(
            0.0,
            candidate.base_weight,
        )
        * (
            confidence
            ** config.facing_power
        )
    )

    if score <= MIN_SCORE:
        return (
            facing_value,
            confidence,
            0.0,
        )

    return (
        facing_value,
        confidence,
        score,
    )


# ---------------------------------------------------------
# Selection + blend
# ---------------------------------------------------------

def blend_candidates(
    candidates: list[
        MaterialColorCandidate
    ],
    config: MaterialBlendConfig,
    *,
    use_absolute_facing: bool = False,
    max_contributors: int | None = None,
) -> MaterialBlendResult:
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
        effective_max_contributors = (
            config.max_contributors
        )
    else:
        if (
            not isinstance(
                max_contributors,
                int,
            )
            or max_contributors <= 0
        ):
            raise ValueError(
                "max_contributors override must be an integer > 0."
            )

        effective_max_contributors = (
            max_contributors
        )

    input_candidate_count = len(
        candidates
    )

    provisional: list[
        tuple[
            MaterialColorCandidate,
            float,
            float,
            float,
        ]
    ] = []

    grazing_rejected_count = 0

    for candidate in candidates:
        (
            facing_value,
            confidence,
            score,
        ) = candidate_score(
            candidate,
            config,
            use_absolute_facing=(
                use_absolute_facing
            ),
        )

        if score <= MIN_SCORE:
            grazing_rejected_count += 1
            continue

        provisional.append(
            (
                candidate,
                facing_value,
                confidence,
                score,
            )
        )

    eligible_candidate_count = len(
        provisional
    )

    if not provisional:
        return MaterialBlendResult(
            color=None,
            scored_candidates=(),
            input_candidate_count=(
                input_candidate_count
            ),
            eligible_candidate_count=0,
            grazing_rejected_count=(
                grazing_rejected_count
            ),
            relative_rejected_count=0,
            top_k_rejected_count=0,
            selected_count=0,
            used_absolute_facing=(
                use_absolute_facing
            ),
        )

    best_score = max(
        score
        for (
            _candidate,
            _facing_value,
            _confidence,
            score,
        ) in provisional
    )

    if best_score <= MIN_SCORE:
        return MaterialBlendResult(
            color=None,
            scored_candidates=(),
            input_candidate_count=(
                input_candidate_count
            ),
            eligible_candidate_count=(
                eligible_candidate_count
            ),
            grazing_rejected_count=(
                grazing_rejected_count
            ),
            relative_rejected_count=0,
            top_k_rejected_count=0,
            selected_count=0,
            used_absolute_facing=(
                use_absolute_facing
            ),
        )

    relative_threshold = (
        best_score
        * config.relative_score_cutoff
    )

    relative_filtered: list[
        tuple[
            MaterialColorCandidate,
            float,
            float,
            float,
            float,
        ]
    ] = []

    relative_rejected_count = 0

    for (
        candidate,
        facing_value,
        confidence,
        score,
    ) in provisional:
        relative_to_best = (
            score / best_score
        )

        if score + MIN_SCORE < relative_threshold:
            relative_rejected_count += 1
            continue

        relative_filtered.append(
            (
                candidate,
                facing_value,
                confidence,
                score,
                relative_to_best,
            )
        )

    if not relative_filtered:
        return MaterialBlendResult(
            color=None,
            scored_candidates=(),
            input_candidate_count=(
                input_candidate_count
            ),
            eligible_candidate_count=(
                eligible_candidate_count
            ),
            grazing_rejected_count=(
                grazing_rejected_count
            ),
            relative_rejected_count=(
                relative_rejected_count
            ),
            top_k_rejected_count=0,
            selected_count=0,
            used_absolute_facing=(
                use_absolute_facing
            ),
        )

    relative_filtered.sort(
        key=lambda item: (
            item[3],  # score
            item[2],  # confidence
            item[1],  # facing_value
            item[0].base_weight,
        ),
        reverse=True,
    )

    selected_raw = relative_filtered[
        :effective_max_contributors
    ]

    top_k_rejected_count = max(
        0,
        len(relative_filtered)
        - len(selected_raw),
    )

    sharpened_total = 0.0
    sharpened_values: list[
        float
    ] = []

    for (
        _candidate,
        _facing_value,
        _confidence,
        score,
        _relative_to_best,
    ) in selected_raw:
        sharpened = (
            max(
                score,
                MIN_WEIGHT,
            )
            ** config.weight_power
        )

        sharpened_values.append(
            sharpened
        )

        sharpened_total += (
            sharpened
        )

    if sharpened_total <= MIN_WEIGHT:
        return MaterialBlendResult(
            color=None,
            scored_candidates=(),
            input_candidate_count=(
                input_candidate_count
            ),
            eligible_candidate_count=(
                eligible_candidate_count
            ),
            grazing_rejected_count=(
                grazing_rejected_count
            ),
            relative_rejected_count=(
                relative_rejected_count
            ),
            top_k_rejected_count=(
                top_k_rejected_count
            ),
            selected_count=0,
            used_absolute_facing=(
                use_absolute_facing
            ),
        )

    scored_candidates: list[
        ScoredMaterialCandidate
    ] = []

    blended_red = 0.0
    blended_green = 0.0
    blended_blue = 0.0
    blended_alpha = 0.0

    for index, (
        candidate,
        facing_value,
        confidence,
        score,
        relative_to_best,
    ) in enumerate(
        selected_raw
    ):
        normalized_weight = (
            sharpened_values[index]
            / sharpened_total
        )

        scored = (
            ScoredMaterialCandidate(
                candidate=candidate,
                facing_value=(
                    facing_value
                ),
                facing_confidence=(
                    confidence
                ),
                score=score,
                relative_to_best=(
                    relative_to_best
                ),
                sharpened_weight=(
                    sharpened_values[index]
                ),
                normalized_weight=(
                    normalized_weight
                ),
            )
        )

        scored_candidates.append(
            scored
        )

        blended_red += (
            candidate.red
            * normalized_weight
        )

        blended_green += (
            candidate.green
            * normalized_weight
        )

        blended_blue += (
            candidate.blue
            * normalized_weight
        )

        blended_alpha += (
            candidate.alpha
            * normalized_weight
        )

    color: Color4 = (
        clamp01(blended_red),
        clamp01(blended_green),
        clamp01(blended_blue),
        clamp01(blended_alpha),
    )

    return MaterialBlendResult(
        color=color,
        scored_candidates=tuple(
            scored_candidates
        ),
        input_candidate_count=(
            input_candidate_count
        ),
        eligible_candidate_count=(
            eligible_candidate_count
        ),
        grazing_rejected_count=(
            grazing_rejected_count
        ),
        relative_rejected_count=(
            relative_rejected_count
        ),
        top_k_rejected_count=(
            top_k_rejected_count
        ),
        selected_count=len(
            scored_candidates
        ),
        used_absolute_facing=(
            use_absolute_facing
        ),
    )


# ---------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------

def choose_best_candidate(
    candidates: list[
        MaterialColorCandidate
    ],
    config: MaterialBlendConfig,
    *,
    use_absolute_facing: bool = False,
) -> MaterialBlendResult:
    """
    Convenience wrapper for fallback-style selection.

    Equivalent to blend_candidates(..., max_contributors=1).
    """

    return blend_candidates(
        candidates,
        config,
        use_absolute_facing=(
            use_absolute_facing
        ),
        max_contributors=1,
    )