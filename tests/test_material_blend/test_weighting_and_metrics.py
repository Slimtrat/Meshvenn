from __future__ import annotations

import math
import sys
import unittest
from core.material_blend import MIN_SCORE, MaterialBlendConfig, MaterialColorCandidate, blend_candidates, candidate_score, choose_best_candidate, clamp01, facing_confidence, smoothstep
from .helpers import default_config, make_candidate

class WeightSharpeningTests(unittest.TestCase):

    def test_weight_power_one_preserves_score_ratio(self) -> None:
        candidates = [make_candidate(source_name='red', red=1.0, green=0.0, blue=0.0, base_weight=1.0), make_candidate(source_name='blue', red=0.0, green=0.0, blue=1.0, base_weight=0.5)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, weight_power=1.0))
        weights = {scored.candidate.source_name: scored.normalized_weight for scored in result.scored_candidates}
        self.assertAlmostEqual(weights['red'], 2.0 / 3.0)
        self.assertAlmostEqual(weights['blue'], 1.0 / 3.0)

    def test_weight_power_two_sharpens_best_candidate(self) -> None:
        candidates = [make_candidate(source_name='red', red=1.0, green=0.0, blue=0.0, base_weight=1.0), make_candidate(source_name='blue', red=0.0, green=0.0, blue=1.0, base_weight=0.5)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, weight_power=2.0))
        weights = {scored.candidate.source_name: scored.normalized_weight for scored in result.scored_candidates}
        self.assertAlmostEqual(weights['red'], 0.8)
        self.assertAlmostEqual(weights['blue'], 0.2)
        self.assertAlmostEqual(result.color[0], 0.8)
        self.assertAlmostEqual(result.color[2], 0.2)

    def test_larger_weight_power_makes_best_more_dominant(self) -> None:
        candidates = [make_candidate(source_name='A', base_weight=1.0), make_candidate(source_name='B', base_weight=0.7)]
        soft = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, weight_power=1.0))
        sharp = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, weight_power=3.0))
        soft_best = soft.scored_candidates[0].normalized_weight
        sharp_best = sharp.scored_candidates[0].normalized_weight
        self.assertGreater(sharp_best, soft_best)

class ColorBlendTests(unittest.TestCase):

    def test_equal_weights_average_colors(self) -> None:
        candidates = [make_candidate(source_name='red', red=1.0, green=0.0, blue=0.0, base_weight=1.0), make_candidate(source_name='blue', red=0.0, green=0.0, blue=1.0, base_weight=1.0)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, weight_power=1.0))
        self.assertIsNotNone(result.color)
        self.assertAlmostEqual(result.color[0], 0.5)
        self.assertAlmostEqual(result.color[1], 0.0)
        self.assertAlmostEqual(result.color[2], 0.5)
        self.assertAlmostEqual(result.color[3], 1.0)

    def test_three_way_blend_is_normalized(self) -> None:
        candidates = [make_candidate(red=1.0, green=0.0, blue=0.0, base_weight=1.0), make_candidate(red=0.0, green=1.0, blue=0.0, base_weight=1.0), make_candidate(red=0.0, green=0.0, blue=1.0, base_weight=1.0)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, weight_power=1.0))
        self.assertAlmostEqual(result.color[0], 1.0 / 3.0)
        self.assertAlmostEqual(result.color[1], 1.0 / 3.0)
        self.assertAlmostEqual(result.color[2], 1.0 / 3.0)
        total_weight = sum((scored.normalized_weight for scored in result.scored_candidates))
        self.assertAlmostEqual(total_weight, 1.0)

    def test_output_color_is_clamped(self) -> None:
        candidate = make_candidate(red=2.0, green=-1.0, blue=1.5, alpha=2.0)
        result = blend_candidates([candidate], default_config())
        self.assertEqual(result.color, (1.0, 0.0, 1.0, 1.0))

class BlendMetricsTests(unittest.TestCase):

    def test_metrics_describe_selection_pipeline(self) -> None:
        candidates = [make_candidate(source_name='A', base_weight=1.0, facing=1.0), make_candidate(source_name='B', base_weight=0.8, facing=1.0), make_candidate(source_name='C', base_weight=0.4, facing=1.0), make_candidate(source_name='D', base_weight=0.1, facing=1.0), make_candidate(source_name='E', base_weight=100.0, facing=0.05)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.2, max_contributors=2, weight_power=1.0))
        self.assertEqual(result.input_candidate_count, 5)
        self.assertEqual(result.eligible_candidate_count, 4)
        self.assertEqual(result.grazing_rejected_count, 1)
        self.assertEqual(result.relative_rejected_count, 1)
        self.assertEqual(result.top_k_rejected_count, 1)
        self.assertEqual(result.selected_count, 2)

class OrderingTests(unittest.TestCase):

    def test_candidates_are_sorted_by_score(self) -> None:
        candidates = [make_candidate(source_name='low', base_weight=0.3), make_candidate(source_name='high', base_weight=1.0), make_candidate(source_name='mid', base_weight=0.6)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, weight_power=1.0))
        names = [scored.candidate.source_name for scored in result.scored_candidates]
        self.assertEqual(names, ['high', 'mid', 'low'])

    def test_equal_candidates_produce_equal_weights(self) -> None:
        candidates = [make_candidate(source_name='A', base_weight=1.0, facing=1.0), make_candidate(source_name='B', base_weight=1.0, facing=1.0), make_candidate(source_name='C', base_weight=1.0, facing=1.0)]
        result = blend_candidates(candidates, default_config(relative_score_cutoff=0.0, max_contributors=3, weight_power=2.0))
        for scored in result.scored_candidates:
            self.assertAlmostEqual(scored.normalized_weight, 1.0 / 3.0)
