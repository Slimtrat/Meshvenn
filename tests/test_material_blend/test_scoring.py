from __future__ import annotations

import math
import sys
import unittest
from core.material_blend import MIN_SCORE, MaterialBlendConfig, MaterialColorCandidate, blend_candidates, candidate_score, choose_best_candidate, clamp01, facing_confidence, smoothstep
from .helpers import default_config, make_candidate

class FacingConfidenceTests(unittest.TestCase):

    def test_below_threshold_has_zero_confidence(self) -> None:
        self.assertEqual(facing_confidence(0.05, min_facing=0.1), 0.0)

    def test_exact_threshold_has_zero_confidence(self) -> None:
        self.assertEqual(facing_confidence(0.1, min_facing=0.1), 0.0)

    def test_full_facing_has_full_confidence(self) -> None:
        self.assertEqual(facing_confidence(1.0, min_facing=0.1), 1.0)

    def test_confidence_increases_smoothly(self) -> None:
        low = facing_confidence(0.25, min_facing=0.1)
        medium = facing_confidence(0.5, min_facing=0.1)
        high = facing_confidence(0.8, min_facing=0.1)
        self.assertGreater(medium, low)
        self.assertGreater(high, medium)

    def test_negative_facing_clamps_to_zero(self) -> None:
        self.assertEqual(facing_confidence(-1.0, min_facing=0.1), 0.0)

class CandidateScoreTests(unittest.TestCase):

    def test_perfect_facing_preserves_base_weight(self) -> None:
        candidate = make_candidate(base_weight=0.75, facing=1.0)
        facing, confidence, score = candidate_score(candidate, default_config())
        self.assertEqual(facing, 1.0)
        self.assertEqual(confidence, 1.0)
        self.assertAlmostEqual(score, 0.75)

    def test_grazing_candidate_has_zero_score(self) -> None:
        candidate = make_candidate(base_weight=1.0, facing=0.05)
        _facing, confidence, score = candidate_score(candidate, default_config())
        self.assertEqual(confidence, 0.0)
        self.assertEqual(score, 0.0)

    def test_negative_facing_is_rejected_in_main_mode(self) -> None:
        candidate = make_candidate(facing=-1.0)
        facing, confidence, score = candidate_score(candidate, default_config())
        self.assertEqual(facing, 0.0)
        self.assertEqual(confidence, 0.0)
        self.assertEqual(score, 0.0)

    def test_negative_facing_can_be_used_for_fallback(self) -> None:
        candidate = make_candidate(facing=-1.0, base_weight=0.8)
        facing, confidence, score = candidate_score(candidate, default_config(), use_absolute_facing=True)
        self.assertEqual(facing, 1.0)
        self.assertEqual(confidence, 1.0)
        self.assertAlmostEqual(score, 0.8)

    def test_facing_power_affects_score(self) -> None:
        candidate = make_candidate(facing=0.55, base_weight=1.0)
        config_one = default_config(facing_power=1.0)
        config_four = default_config(facing_power=4.0)
        _, _, score_one = candidate_score(candidate, config_one)
        _, _, score_four = candidate_score(candidate, config_four)
        self.assertGreater(score_one, score_four)

    def test_zero_base_weight_produces_zero_score(self) -> None:
        candidate = make_candidate(base_weight=0.0, facing=1.0)
        _, _, score = candidate_score(candidate, default_config())
        self.assertEqual(score, 0.0)

class FacingRankingTests(unittest.TestCase):

    def test_better_facing_can_beat_equal_base_weight(self) -> None:
        candidates = [make_candidate(source_name='front', facing=1.0, base_weight=1.0), make_candidate(source_name='angled', facing=0.5, base_weight=1.0)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, weight_power=1.0))
        self.assertEqual(result.scored_candidates[0].candidate.source_name, 'front')
        front_weight = result.scored_candidates[0].normalized_weight
        angled_weight = result.scored_candidates[1].normalized_weight
        self.assertGreater(front_weight, angled_weight)

    def test_strong_base_weight_does_not_rescue_grazing_view(self) -> None:
        candidates = [make_candidate(source_name='front', facing=1.0, base_weight=1.0), make_candidate(source_name='grazing', facing=0.05, base_weight=1000.0)]
        result = blend_candidates(candidates, default_config())
        names = [scored.candidate.source_name for scored in result.scored_candidates]
        self.assertEqual(names, ['front'])
        self.assertEqual(result.grazing_rejected_count, 1)

class AbsoluteFacingTests(unittest.TestCase):

    def test_backfacing_candidates_are_ignored_normally(self) -> None:
        candidates = [make_candidate(source_name='back', facing=-1.0)]
        result = blend_candidates(candidates, default_config())
        self.assertFalse(result.has_selection)

    def test_backfacing_candidate_is_available_in_absolute_mode(self) -> None:
        candidates = [make_candidate(source_name='back', facing=-1.0, red=0.2, green=0.5, blue=0.7)]
        result = blend_candidates(candidates, default_config(), use_absolute_facing=True)
        self.assertTrue(result.has_selection)
        self.assertTrue(result.used_absolute_facing)
        self.assertEqual(result.selected_count, 1)
        self.assertEqual(result.color, (0.2, 0.5, 0.7, 1.0))

    def test_absolute_mode_prefers_most_aligned_backface(self) -> None:
        candidates = [make_candidate(source_name='weak', facing=-0.4, base_weight=1.0), make_candidate(source_name='strong', facing=-1.0, base_weight=1.0)]
        result = choose_best_candidate(candidates, default_config(relative_score_cutoff=0.0), use_absolute_facing=True)
        self.assertEqual(result.selected_count, 1)
        self.assertEqual(result.scored_candidates[0].candidate.source_name, 'strong')
