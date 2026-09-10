from __future__ import annotations

import math
import sys
import unittest

from pathlib import Path


# ---------------------------------------------------------
# Repository import
# ---------------------------------------------------------

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from core.material_blend import (
    MIN_SCORE,
    MaterialBlendConfig,
    MaterialColorCandidate,
    blend_candidates,
    candidate_score,
    choose_best_candidate,
    clamp01,
    facing_confidence,
    smoothstep,
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def make_candidate(
    *,
    red: float = 1.0,
    green: float = 0.0,
    blue: float = 0.0,
    alpha: float = 1.0,
    base_weight: float = 1.0,
    facing: float = 1.0,
    source_name: str = "view",
) -> MaterialColorCandidate:
    return MaterialColorCandidate(
        red=red,
        green=green,
        blue=blue,
        alpha=alpha,
        base_weight=base_weight,
        facing=facing,
        source_name=source_name,
    )


def default_config(
    **overrides,
) -> MaterialBlendConfig:
    values = {
        "min_facing": 0.10,
        "facing_power": 2.0,
        "relative_score_cutoff": 0.20,
        "max_contributors": 3,
        "weight_power": 1.5,
    }

    values.update(
        overrides
    )

    return MaterialBlendConfig(
        **values
    )


# ---------------------------------------------------------
# clamp01
# ---------------------------------------------------------

class ClampTests(
    unittest.TestCase
):
    def test_value_inside_range_is_unchanged(
        self,
    ) -> None:
        self.assertEqual(
            clamp01(
                0.42
            ),
            0.42,
        )

    def test_negative_value_is_clamped_to_zero(
        self,
    ) -> None:
        self.assertEqual(
            clamp01(
                -10.0
            ),
            0.0,
        )

    def test_value_above_one_is_clamped_to_one(
        self,
    ) -> None:
        self.assertEqual(
            clamp01(
                12.0
            ),
            1.0,
        )

    def test_boundaries_are_preserved(
        self,
    ) -> None:
        self.assertEqual(
            clamp01(
                0.0
            ),
            0.0,
        )

        self.assertEqual(
            clamp01(
                1.0
            ),
            1.0,
        )


# ---------------------------------------------------------
# smoothstep
# ---------------------------------------------------------

class SmoothstepTests(
    unittest.TestCase
):
    def test_below_lower_edge_returns_zero(
        self,
    ) -> None:
        self.assertEqual(
            smoothstep(
                0.2,
                0.8,
                0.1,
            ),
            0.0,
        )

    def test_above_upper_edge_returns_one(
        self,
    ) -> None:
        self.assertEqual(
            smoothstep(
                0.2,
                0.8,
                0.9,
            ),
            1.0,
        )

    def test_lower_edge_returns_zero(
        self,
    ) -> None:
        self.assertEqual(
            smoothstep(
                0.2,
                0.8,
                0.2,
            ),
            0.0,
        )

    def test_upper_edge_returns_one(
        self,
    ) -> None:
        self.assertEqual(
            smoothstep(
                0.2,
                0.8,
                0.8,
            ),
            1.0,
        )

    def test_midpoint_returns_half(
        self,
    ) -> None:
        self.assertAlmostEqual(
            smoothstep(
                0.0,
                1.0,
                0.5,
            ),
            0.5,
        )

    def test_equal_edges_behave_like_step(
        self,
    ) -> None:
        self.assertEqual(
            smoothstep(
                0.5,
                0.5,
                0.49,
            ),
            0.0,
        )

        self.assertEqual(
            smoothstep(
                0.5,
                0.5,
                0.5,
            ),
            1.0,
        )

        self.assertEqual(
            smoothstep(
                0.5,
                0.5,
                0.9,
            ),
            1.0,
        )

    def test_reversed_edges_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            smoothstep(
                0.8,
                0.2,
                0.5,
            )

    def test_non_finite_values_are_rejected(
        self,
    ) -> None:
        cases = [
            (
                math.inf,
                1.0,
                0.5,
            ),
            (
                0.0,
                math.inf,
                0.5,
            ),
            (
                0.0,
                1.0,
                math.inf,
            ),
            (
                math.nan,
                1.0,
                0.5,
            ),
        ]

        for (
            edge0,
            edge1,
            value,
        ) in cases:
            with self.subTest(
                edge0=edge0,
                edge1=edge1,
                value=value,
            ):
                with self.assertRaises(
                    ValueError
                ):
                    smoothstep(
                        edge0,
                        edge1,
                        value,
                    )


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

class MaterialBlendConfigTests(
    unittest.TestCase
):
    def test_default_configuration_is_valid(
        self,
    ) -> None:
        config = (
            MaterialBlendConfig()
        )

        config.validate()

    def test_min_facing_accepts_boundaries(
        self,
    ) -> None:
        for value in (
            0.0,
            1.0,
        ):
            with self.subTest(
                value=value
            ):
                config = (
                    default_config(
                        min_facing=value
                    )
                )

                config.validate()

    def test_invalid_min_facing_is_rejected(
        self,
    ) -> None:
        for value in (
            -0.1,
            1.1,
            math.inf,
            math.nan,
        ):
            with self.subTest(
                value=value
            ):
                config = (
                    default_config(
                        min_facing=value
                    )
                )

                with self.assertRaises(
                    ValueError
                ):
                    config.validate()

    def test_zero_facing_power_is_allowed(
        self,
    ) -> None:
        config = (
            default_config(
                facing_power=0.0
            )
        )

        config.validate()

    def test_negative_facing_power_is_rejected(
        self,
    ) -> None:
        config = (
            default_config(
                facing_power=-1.0
            )
        )

        with self.assertRaises(
            ValueError
        ):
            config.validate()

    def test_relative_cutoff_accepts_boundaries(
        self,
    ) -> None:
        for value in (
            0.0,
            1.0,
        ):
            with self.subTest(
                value=value
            ):
                config = (
                    default_config(
                        relative_score_cutoff=value
                    )
                )

                config.validate()

    def test_invalid_relative_cutoff_is_rejected(
        self,
    ) -> None:
        for value in (
            -0.01,
            1.01,
            math.inf,
            math.nan,
        ):
            with self.subTest(
                value=value
            ):
                config = (
                    default_config(
                        relative_score_cutoff=value
                    )
                )

                with self.assertRaises(
                    ValueError
                ):
                    config.validate()

    def test_max_contributors_must_be_positive(
        self,
    ) -> None:
        for value in (
            0,
            -1,
            -50,
        ):
            with self.subTest(
                value=value
            ):
                config = (
                    default_config(
                        max_contributors=value
                    )
                )

                with self.assertRaises(
                    ValueError
                ):
                    config.validate()

    def test_weight_power_must_be_positive(
        self,
    ) -> None:
        for value in (
            0.0,
            -1.0,
            math.inf,
            math.nan,
        ):
            with self.subTest(
                value=value
            ):
                config = (
                    default_config(
                        weight_power=value
                    )
                )

                with self.assertRaises(
                    ValueError
                ):
                    config.validate()


# ---------------------------------------------------------
# Candidate validation
# ---------------------------------------------------------

class CandidateValidationTests(
    unittest.TestCase
):
    def test_valid_candidate_passes(
        self,
    ) -> None:
        candidate = (
            make_candidate()
        )

        candidate.validate()

    def test_negative_base_weight_is_rejected(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                base_weight=-1.0
            )
        )

        with self.assertRaises(
            ValueError
        ):
            candidate.validate()

    def test_non_finite_values_are_rejected(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                red=math.inf
            ),
            make_candidate(
                green=math.nan
            ),
            make_candidate(
                blue=math.inf
            ),
            make_candidate(
                alpha=math.nan
            ),
            make_candidate(
                base_weight=math.inf
            ),
            make_candidate(
                facing=math.nan
            ),
        ]

        for candidate in candidates:
            with self.subTest(
                candidate=candidate
            ):
                with self.assertRaises(
                    ValueError
                ):
                    candidate.validate()

    def test_color_property_clamps_channels(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                red=-1.0,
                green=0.5,
                blue=2.0,
                alpha=1.5,
            )
        )

        self.assertEqual(
            candidate.color,
            (
                0.0,
                0.5,
                1.0,
                1.0,
            ),
        )


# ---------------------------------------------------------
# Facing confidence
# ---------------------------------------------------------

class FacingConfidenceTests(
    unittest.TestCase
):
    def test_below_threshold_has_zero_confidence(
        self,
    ) -> None:
        self.assertEqual(
            facing_confidence(
                0.05,
                min_facing=0.10,
            ),
            0.0,
        )

    def test_exact_threshold_has_zero_confidence(
        self,
    ) -> None:
        self.assertEqual(
            facing_confidence(
                0.10,
                min_facing=0.10,
            ),
            0.0,
        )

    def test_full_facing_has_full_confidence(
        self,
    ) -> None:
        self.assertEqual(
            facing_confidence(
                1.0,
                min_facing=0.10,
            ),
            1.0,
        )

    def test_confidence_increases_smoothly(
        self,
    ) -> None:
        low = facing_confidence(
            0.25,
            min_facing=0.10,
        )

        medium = facing_confidence(
            0.50,
            min_facing=0.10,
        )

        high = facing_confidence(
            0.80,
            min_facing=0.10,
        )

        self.assertGreater(
            medium,
            low,
        )

        self.assertGreater(
            high,
            medium,
        )

    def test_negative_facing_clamps_to_zero(
        self,
    ) -> None:
        self.assertEqual(
            facing_confidence(
                -1.0,
                min_facing=0.10,
            ),
            0.0,
        )


# ---------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------

class CandidateScoreTests(
    unittest.TestCase
):
    def test_perfect_facing_preserves_base_weight(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                base_weight=0.75,
                facing=1.0,
            )
        )

        (
            facing,
            confidence,
            score,
        ) = candidate_score(
            candidate,
            default_config(),
        )

        self.assertEqual(
            facing,
            1.0,
        )

        self.assertEqual(
            confidence,
            1.0,
        )

        self.assertAlmostEqual(
            score,
            0.75,
        )

    def test_grazing_candidate_has_zero_score(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                base_weight=1.0,
                facing=0.05,
            )
        )

        (
            _facing,
            confidence,
            score,
        ) = candidate_score(
            candidate,
            default_config(),
        )

        self.assertEqual(
            confidence,
            0.0,
        )

        self.assertEqual(
            score,
            0.0,
        )

    def test_negative_facing_is_rejected_in_main_mode(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                facing=-1.0
            )
        )

        (
            facing,
            confidence,
            score,
        ) = candidate_score(
            candidate,
            default_config(),
        )

        self.assertEqual(
            facing,
            0.0,
        )

        self.assertEqual(
            confidence,
            0.0,
        )

        self.assertEqual(
            score,
            0.0,
        )

    def test_negative_facing_can_be_used_for_fallback(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                facing=-1.0,
                base_weight=0.8,
            )
        )

        (
            facing,
            confidence,
            score,
        ) = candidate_score(
            candidate,
            default_config(),
            use_absolute_facing=True,
        )

        self.assertEqual(
            facing,
            1.0,
        )

        self.assertEqual(
            confidence,
            1.0,
        )

        self.assertAlmostEqual(
            score,
            0.8,
        )

    def test_facing_power_affects_score(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                facing=0.55,
                base_weight=1.0,
            )
        )

        config_one = (
            default_config(
                facing_power=1.0
            )
        )

        config_four = (
            default_config(
                facing_power=4.0
            )
        )

        (
            _,
            _,
            score_one,
        ) = candidate_score(
            candidate,
            config_one,
        )

        (
            _,
            _,
            score_four,
        ) = candidate_score(
            candidate,
            config_four,
        )

        self.assertGreater(
            score_one,
            score_four,
        )

    def test_zero_base_weight_produces_zero_score(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                base_weight=0.0,
                facing=1.0,
            )
        )

        (
            _,
            _,
            score,
        ) = candidate_score(
            candidate,
            default_config(),
        )

        self.assertEqual(
            score,
            0.0,
        )


# ---------------------------------------------------------
# Empty selection
# ---------------------------------------------------------

class EmptyBlendTests(
    unittest.TestCase
):
    def test_no_candidates_returns_empty_result(
        self,
    ) -> None:
        result = (
            blend_candidates(
                [],
                default_config(),
            )
        )

        self.assertIsNone(
            result.color
        )

        self.assertFalse(
            result.has_selection
        )

        self.assertEqual(
            result.input_candidate_count,
            0,
        )

        self.assertEqual(
            result.selected_count,
            0,
        )

    def test_all_grazing_candidates_return_empty_result(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                facing=0.0
            ),
            make_candidate(
                facing=0.01
            ),
            make_candidate(
                facing=0.10
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(),
            )
        )

        self.assertIsNone(
            result.color
        )

        self.assertEqual(
            result.input_candidate_count,
            3,
        )

        self.assertEqual(
            result.eligible_candidate_count,
            0,
        )

        self.assertEqual(
            result.grazing_rejected_count,
            3,
        )


# ---------------------------------------------------------
# Single candidate
# ---------------------------------------------------------

class SingleCandidateTests(
    unittest.TestCase
):
    def test_single_candidate_is_selected(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                red=0.2,
                green=0.4,
                blue=0.8,
                alpha=1.0,
                facing=1.0,
            )
        )

        result = (
            blend_candidates(
                [
                    candidate
                ],
                default_config(),
            )
        )

        self.assertTrue(
            result.has_selection
        )

        self.assertEqual(
            result.selected_count,
            1,
        )

        self.assertEqual(
            result.color,
            (
                0.2,
                0.4,
                0.8,
                1.0,
            ),
        )

        scored = (
            result
            .scored_candidates[0]
        )

        self.assertAlmostEqual(
            scored.normalized_weight,
            1.0,
        )

        self.assertAlmostEqual(
            scored.relative_to_best,
            1.0,
        )


# ---------------------------------------------------------
# Relative cutoff
# ---------------------------------------------------------

class RelativeCutoffTests(
    unittest.TestCase
):
    def test_candidate_below_relative_cutoff_is_removed(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="best",
                base_weight=1.0,
                facing=1.0,
            ),
            make_candidate(
                source_name="weak",
                base_weight=0.19,
                facing=1.0,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.20,
                    weight_power=1.0,
                ),
            )
        )

        self.assertEqual(
            result.eligible_candidate_count,
            2,
        )

        self.assertEqual(
            result.relative_rejected_count,
            1,
        )

        self.assertEqual(
            result.selected_count,
            1,
        )

        self.assertEqual(
            result
            .scored_candidates[0]
            .candidate
            .source_name,
            "best",
        )

    def test_candidate_exactly_at_relative_cutoff_is_kept(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="best",
                base_weight=1.0,
                facing=1.0,
            ),
            make_candidate(
                source_name="boundary",
                base_weight=0.20,
                facing=1.0,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.20,
                    weight_power=1.0,
                ),
            )
        )

        self.assertEqual(
            result.relative_rejected_count,
            0,
        )

        self.assertEqual(
            result.selected_count,
            2,
        )

    def test_zero_cutoff_keeps_every_eligible_candidate(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="A",
                base_weight=1.0,
            ),
            make_candidate(
                source_name="B",
                base_weight=0.01,
            ),
            make_candidate(
                source_name="C",
                base_weight=0.001,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    max_contributors=10,
                ),
            )
        )

        self.assertEqual(
            result.relative_rejected_count,
            0,
        )

        self.assertEqual(
            result.selected_count,
            3,
        )

    def test_cutoff_one_keeps_only_best_score(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="best",
                base_weight=1.0,
            ),
            make_candidate(
                source_name="B",
                base_weight=0.8,
            ),
            make_candidate(
                source_name="C",
                base_weight=0.5,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=1.0,
                    max_contributors=10,
                ),
            )
        )

        self.assertEqual(
            result.selected_count,
            1,
        )

        self.assertEqual(
            result.relative_rejected_count,
            2,
        )


# ---------------------------------------------------------
# Top-K selection
# ---------------------------------------------------------

class TopKTests(
    unittest.TestCase
):
    def test_only_top_three_candidates_are_kept(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="A",
                base_weight=1.0,
            ),
            make_candidate(
                source_name="B",
                base_weight=0.8,
            ),
            make_candidate(
                source_name="C",
                base_weight=0.6,
            ),
            make_candidate(
                source_name="D",
                base_weight=0.4,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    max_contributors=3,
                    weight_power=1.0,
                ),
            )
        )

        self.assertEqual(
            result.selected_count,
            3,
        )

        self.assertEqual(
            result.top_k_rejected_count,
            1,
        )

        names = [
            scored
            .candidate
            .source_name
            for scored
            in result.scored_candidates
        ]

        self.assertEqual(
            names,
            [
                "A",
                "B",
                "C",
            ],
        )

    def test_override_can_force_one_contributor(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="A",
                base_weight=1.0,
            ),
            make_candidate(
                source_name="B",
                base_weight=0.9,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    max_contributors=3
                ),
                max_contributors=1,
            )
        )

        self.assertEqual(
            result.selected_count,
            1,
        )

        self.assertEqual(
            result.top_k_rejected_count,
            1,
        )

        self.assertEqual(
            result
            .scored_candidates[0]
            .candidate
            .source_name,
            "A",
        )

    def test_invalid_override_is_rejected(
        self,
    ) -> None:
        for value in (
            0,
            -1,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    blend_candidates(
                        [
                            make_candidate()
                        ],
                        default_config(),
                        max_contributors=value,
                    )


# ---------------------------------------------------------
# Weight sharpening
# ---------------------------------------------------------

class WeightSharpeningTests(
    unittest.TestCase
):
    def test_weight_power_one_preserves_score_ratio(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="red",
                red=1.0,
                green=0.0,
                blue=0.0,
                base_weight=1.0,
            ),
            make_candidate(
                source_name="blue",
                red=0.0,
                green=0.0,
                blue=1.0,
                base_weight=0.5,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    weight_power=1.0,
                ),
            )
        )

        weights = {
            scored
            .candidate
            .source_name:
            scored
            .normalized_weight
            for scored
            in result.scored_candidates
        }

        self.assertAlmostEqual(
            weights["red"],
            2.0 / 3.0,
        )

        self.assertAlmostEqual(
            weights["blue"],
            1.0 / 3.0,
        )

    def test_weight_power_two_sharpens_best_candidate(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="red",
                red=1.0,
                green=0.0,
                blue=0.0,
                base_weight=1.0,
            ),
            make_candidate(
                source_name="blue",
                red=0.0,
                green=0.0,
                blue=1.0,
                base_weight=0.5,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    weight_power=2.0,
                ),
            )
        )

        weights = {
            scored
            .candidate
            .source_name:
            scored
            .normalized_weight
            for scored
            in result.scored_candidates
        }

        # 1² / (1² + 0.5²)
        self.assertAlmostEqual(
            weights["red"],
            0.8,
        )

        # 0.5² / (1² + 0.5²)
        self.assertAlmostEqual(
            weights["blue"],
            0.2,
        )

        self.assertAlmostEqual(
            result.color[0],
            0.8,
        )

        self.assertAlmostEqual(
            result.color[2],
            0.2,
        )

    def test_larger_weight_power_makes_best_more_dominant(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="A",
                base_weight=1.0,
            ),
            make_candidate(
                source_name="B",
                base_weight=0.7,
            ),
        ]

        soft = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    weight_power=1.0,
                ),
            )
        )

        sharp = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    weight_power=3.0,
                ),
            )
        )

        soft_best = (
            soft
            .scored_candidates[0]
            .normalized_weight
        )

        sharp_best = (
            sharp
            .scored_candidates[0]
            .normalized_weight
        )

        self.assertGreater(
            sharp_best,
            soft_best,
        )


# ---------------------------------------------------------
# Color blending
# ---------------------------------------------------------

class ColorBlendTests(
    unittest.TestCase
):
    def test_equal_weights_average_colors(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="red",
                red=1.0,
                green=0.0,
                blue=0.0,
                base_weight=1.0,
            ),
            make_candidate(
                source_name="blue",
                red=0.0,
                green=0.0,
                blue=1.0,
                base_weight=1.0,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    weight_power=1.0,
                ),
            )
        )

        self.assertIsNotNone(
            result.color
        )

        self.assertAlmostEqual(
            result.color[0],
            0.5,
        )

        self.assertAlmostEqual(
            result.color[1],
            0.0,
        )

        self.assertAlmostEqual(
            result.color[2],
            0.5,
        )

        self.assertAlmostEqual(
            result.color[3],
            1.0,
        )

    def test_three_way_blend_is_normalized(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                red=1.0,
                green=0.0,
                blue=0.0,
                base_weight=1.0,
            ),
            make_candidate(
                red=0.0,
                green=1.0,
                blue=0.0,
                base_weight=1.0,
            ),
            make_candidate(
                red=0.0,
                green=0.0,
                blue=1.0,
                base_weight=1.0,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    weight_power=1.0,
                ),
            )
        )

        self.assertAlmostEqual(
            result.color[0],
            1.0 / 3.0,
        )

        self.assertAlmostEqual(
            result.color[1],
            1.0 / 3.0,
        )

        self.assertAlmostEqual(
            result.color[2],
            1.0 / 3.0,
        )

        total_weight = sum(
            scored.normalized_weight
            for scored
            in result.scored_candidates
        )

        self.assertAlmostEqual(
            total_weight,
            1.0,
        )

    def test_output_color_is_clamped(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                red=2.0,
                green=-1.0,
                blue=1.5,
                alpha=2.0,
            )
        )

        result = (
            blend_candidates(
                [
                    candidate
                ],
                default_config(),
            )
        )

        self.assertEqual(
            result.color,
            (
                1.0,
                0.0,
                1.0,
                1.0,
            ),
        )


# ---------------------------------------------------------
# Facing influences ranking
# ---------------------------------------------------------

class FacingRankingTests(
    unittest.TestCase
):
    def test_better_facing_can_beat_equal_base_weight(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="front",
                facing=1.0,
                base_weight=1.0,
            ),
            make_candidate(
                source_name="angled",
                facing=0.5,
                base_weight=1.0,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    weight_power=1.0,
                ),
            )
        )

        self.assertEqual(
            result
            .scored_candidates[0]
            .candidate
            .source_name,
            "front",
        )

        front_weight = (
            result
            .scored_candidates[0]
            .normalized_weight
        )

        angled_weight = (
            result
            .scored_candidates[1]
            .normalized_weight
        )

        self.assertGreater(
            front_weight,
            angled_weight,
        )

    def test_strong_base_weight_does_not_rescue_grazing_view(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="front",
                facing=1.0,
                base_weight=1.0,
            ),
            make_candidate(
                source_name="grazing",
                facing=0.05,
                base_weight=1000.0,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(),
            )
        )

        names = [
            scored
            .candidate
            .source_name
            for scored
            in result.scored_candidates
        ]

        self.assertEqual(
            names,
            [
                "front"
            ],
        )

        self.assertEqual(
            result.grazing_rejected_count,
            1,
        )


# ---------------------------------------------------------
# Absolute-facing fallback
# ---------------------------------------------------------

class AbsoluteFacingTests(
    unittest.TestCase
):
    def test_backfacing_candidates_are_ignored_normally(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="back",
                facing=-1.0,
            )
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(),
            )
        )

        self.assertFalse(
            result.has_selection
        )

    def test_backfacing_candidate_is_available_in_absolute_mode(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="back",
                facing=-1.0,
                red=0.2,
                green=0.5,
                blue=0.7,
            )
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(),
                use_absolute_facing=True,
            )
        )

        self.assertTrue(
            result.has_selection
        )

        self.assertTrue(
            result.used_absolute_facing
        )

        self.assertEqual(
            result.selected_count,
            1,
        )

        self.assertEqual(
            result.color,
            (
                0.2,
                0.5,
                0.7,
                1.0,
            ),
        )

    def test_absolute_mode_prefers_most_aligned_backface(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="weak",
                facing=-0.4,
                base_weight=1.0,
            ),
            make_candidate(
                source_name="strong",
                facing=-1.0,
                base_weight=1.0,
            ),
        ]

        result = (
            choose_best_candidate(
                candidates,
                default_config(
                    relative_score_cutoff=0.0
                ),
                use_absolute_facing=True,
            )
        )

        self.assertEqual(
            result.selected_count,
            1,
        )

        self.assertEqual(
            result
            .scored_candidates[0]
            .candidate
            .source_name,
            "strong",
        )


# ---------------------------------------------------------
# Best-candidate helper
# ---------------------------------------------------------

class BestCandidateTests(
    unittest.TestCase
):
    def test_choose_best_candidate_forces_top_one(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="A",
                base_weight=0.5,
            ),
            make_candidate(
                source_name="B",
                base_weight=1.0,
            ),
            make_candidate(
                source_name="C",
                base_weight=0.8,
            ),
        ]

        result = (
            choose_best_candidate(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    max_contributors=10,
                ),
            )
        )

        self.assertEqual(
            result.selected_count,
            1,
        )

        self.assertEqual(
            result
            .scored_candidates[0]
            .candidate
            .source_name,
            "B",
        )

        self.assertEqual(
            result.top_k_rejected_count,
            2,
        )


# ---------------------------------------------------------
# Metrics
# ---------------------------------------------------------

class BlendMetricsTests(
    unittest.TestCase
):
    def test_metrics_describe_selection_pipeline(
        self,
    ) -> None:
        candidates = [
            # Selected
            make_candidate(
                source_name="A",
                base_weight=1.0,
                facing=1.0,
            ),

            # Selected
            make_candidate(
                source_name="B",
                base_weight=0.8,
                facing=1.0,
            ),

            # Survives relative cutoff,
            # removed by top-K.
            make_candidate(
                source_name="C",
                base_weight=0.4,
                facing=1.0,
            ),

            # Relative cutoff.
            make_candidate(
                source_name="D",
                base_weight=0.1,
                facing=1.0,
            ),

            # Grazing.
            make_candidate(
                source_name="E",
                base_weight=100.0,
                facing=0.05,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.2,
                    max_contributors=2,
                    weight_power=1.0,
                ),
            )
        )

        self.assertEqual(
            result.input_candidate_count,
            5,
        )

        self.assertEqual(
            result.eligible_candidate_count,
            4,
        )

        self.assertEqual(
            result.grazing_rejected_count,
            1,
        )

        self.assertEqual(
            result.relative_rejected_count,
            1,
        )

        self.assertEqual(
            result.top_k_rejected_count,
            1,
        )

        self.assertEqual(
            result.selected_count,
            2,
        )


# ---------------------------------------------------------
# Stability / ordering
# ---------------------------------------------------------

class OrderingTests(
    unittest.TestCase
):
    def test_candidates_are_sorted_by_score(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="low",
                base_weight=0.3,
            ),
            make_candidate(
                source_name="high",
                base_weight=1.0,
            ),
            make_candidate(
                source_name="mid",
                base_weight=0.6,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    weight_power=1.0,
                ),
            )
        )

        names = [
            scored
            .candidate
            .source_name
            for scored
            in result.scored_candidates
        ]

        self.assertEqual(
            names,
            [
                "high",
                "mid",
                "low",
            ],
        )

    def test_equal_candidates_produce_equal_weights(
        self,
    ) -> None:
        candidates = [
            make_candidate(
                source_name="A",
                base_weight=1.0,
                facing=1.0,
            ),
            make_candidate(
                source_name="B",
                base_weight=1.0,
                facing=1.0,
            ),
            make_candidate(
                source_name="C",
                base_weight=1.0,
                facing=1.0,
            ),
        ]

        result = (
            blend_candidates(
                candidates,
                default_config(
                    relative_score_cutoff=0.0,
                    max_contributors=3,
                    weight_power=2.0,
                ),
            )
        )

        for scored in (
            result.scored_candidates
        ):
            self.assertAlmostEqual(
                scored.normalized_weight,
                1.0 / 3.0,
            )


# ---------------------------------------------------------
# MIN_SCORE behaviour
# ---------------------------------------------------------

class MinimumScoreTests(
    unittest.TestCase
):
    def test_tiny_weight_is_treated_as_zero(
        self,
    ) -> None:
        candidate = (
            make_candidate(
                base_weight=(
                    MIN_SCORE
                    * 0.1
                ),
                facing=1.0,
            )
        )

        result = (
            blend_candidates(
                [
                    candidate
                ],
                default_config(),
            )
        )

        self.assertFalse(
            result.has_selection
        )

        self.assertEqual(
            result.grazing_rejected_count,
            1,
        )


# ---------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------

if __name__ == "__main__":
    unittest.main()