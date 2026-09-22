from __future__ import annotations

import math
import sys
import unittest
from core.material_blend import MIN_SCORE, MaterialBlendConfig, MaterialColorCandidate, blend_candidates, candidate_score, choose_best_candidate, clamp01, facing_confidence, smoothstep
from .helpers import default_config, make_candidate

class EmptyBlendTests(unittest.TestCase):

    def test_no_candidates_returns_empty_result(self) -> None:
        result = blend_candidates([], default_config())
        self.assertIsNone(result.color)
        self.assertFalse(result.has_selection)
        self.assertEqual(result.input_candidate_count, 0)
        self.assertEqual(result.selected_count, 0)

    def test_all_grazing_candidates_return_empty_result(self) -> None:
        candidates = [make_candidate(facing=0.0), make_candidate(facing=0.01), make_candidate(facing=0.1)]
        result = blend_candidates(candidates, default_config())
        self.assertIsNone(result.color)
        self.assertEqual(result.input_candidate_count, 3)
        self.assertEqual(result.eligible_candidate_count, 0)
        self.assertEqual(result.grazing_rejected_count, 3)

class SingleCandidateTests(unittest.TestCase):

    def test_single_candidate_is_selected(self) -> None:
        candidate = make_candidate(red=0.2, green=0.4, blue=0.8, alpha=1.0, facing=1.0)
        result = blend_candidates([candidate], default_config())
        self.assertTrue(result.has_selection)
        self.assertEqual(result.selected_count, 1)
        self.assertEqual(result.color, (0.2, 0.4, 0.8, 1.0))
        scored = result.scored_candidates[0]
        self.assertAlmostEqual(scored.normalized_weight, 1.0)
        self.assertAlmostEqual(scored.relative_to_best, 1.0)

class RelativeCutoffTests(unittest.TestCase):

    def test_candidate_below_relative_cutoff_is_removed(self) -> None:
        candidates = [make_candidate(source_name='best', base_weight=1.0, facing=1.0), make_candidate(source_name='weak', base_weight=0.19, facing=1.0)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.2, weight_power=1.0))
        self.assertEqual(result.eligible_candidate_count, 2)
        self.assertEqual(result.relative_rejected_count, 1)
        self.assertEqual(result.selected_count, 1)
        self.assertEqual(result.scored_candidates[0].candidate.source_name, 'best')

    def test_candidate_exactly_at_relative_cutoff_is_kept(self) -> None:
        candidates = [make_candidate(source_name='best', base_weight=1.0, facing=1.0), make_candidate(source_name='boundary', base_weight=0.2, facing=1.0)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.2, weight_power=1.0))
        self.assertEqual(result.relative_rejected_count, 0)
        self.assertEqual(result.selected_count, 2)

    def test_zero_cutoff_keeps_every_eligible_candidate(self) -> None:
        candidates = [make_candidate(source_name='A', base_weight=1.0), make_candidate(source_name='B', base_weight=0.01), make_candidate(source_name='C', base_weight=0.001)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, max_contributors=10))
        self.assertEqual(result.relative_rejected_count, 0)
        self.assertEqual(result.selected_count, 3)

    def test_cutoff_one_keeps_only_best_score(self) -> None:
        candidates = [make_candidate(source_name='best', base_weight=1.0), make_candidate(source_name='B', base_weight=0.8), make_candidate(source_name='C', base_weight=0.5)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=1.0, max_contributors=10))
        self.assertEqual(result.selected_count, 1)
        self.assertEqual(result.relative_rejected_count, 2)

class TopKTests(unittest.TestCase):

    def test_only_top_three_candidates_are_kept(self) -> None:
        candidates = [make_candidate(source_name='A', base_weight=1.0), make_candidate(source_name='B', base_weight=0.8), make_candidate(source_name='C', base_weight=0.6), make_candidate(source_name='D', base_weight=0.4)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, max_contributors=3, weight_power=1.0))
        self.assertEqual(result.selected_count, 3)
        self.assertEqual(result.top_k_rejected_count, 1)
        names = [scored.candidate.source_name for scored in result.scored_candidates]
        self.assertEqual(names, ['A', 'B', 'C'])

    def test_override_can_force_one_contributor(self) -> None:
        candidates = [make_candidate(source_name='A', base_weight=1.0), make_candidate(source_name='B', base_weight=0.9)]
        result = blend_candidates(candidates, default_config(max_contributors=3), max_contributors=1)
        self.assertEqual(result.selected_count, 1)
        self.assertEqual(result.top_k_rejected_count, 1)
        self.assertEqual(result.scored_candidates[0].candidate.source_name, 'A')

    def test_invalid_override_is_rejected(self) -> None:
        for value in (0, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    blend_candidates([make_candidate()], default_config(), max_contributors=value)

class BestCandidateTests(unittest.TestCase):

    def test_choose_best_candidate_forces_top_one(self) -> None:
        candidates = [make_candidate(source_name='A', base_weight=0.5), make_candidate(source_name='B', base_weight=1.0), make_candidate(source_name='C', base_weight=0.8)]
        result = choose_best_candidate(candidates, default_config(relative_score_cutoff=0.0, max_contributors=10))
        self.assertEqual(result.selected_count, 1)
        self.assertEqual(result.scored_candidates[0].candidate.source_name, 'B')
        self.assertEqual(result.top_k_rejected_count, 2)

class MinimumScoreTests(unittest.TestCase):

    def test_tiny_weight_is_treated_as_zero(self) -> None:
        candidate = make_candidate(base_weight=MIN_SCORE * 0.1, facing=1.0)
        result = blend_candidates([candidate], default_config())
        self.assertFalse(result.has_selection)
        self.assertEqual(result.grazing_rejected_count, 1)
