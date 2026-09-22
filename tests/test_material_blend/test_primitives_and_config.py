from __future__ import annotations

import math
import sys
import unittest
from core.material_blend import MIN_SCORE, MaterialBlendConfig, MaterialColorCandidate, blend_candidates, candidate_score, choose_best_candidate, clamp01, facing_confidence, smoothstep
from .helpers import default_config, make_candidate

class ClampTests(unittest.TestCase):

    def test_value_inside_range_is_unchanged(self) -> None:
        self.assertEqual(clamp01(0.42), 0.42)

    def test_negative_value_is_clamped_to_zero(self) -> None:
        self.assertEqual(clamp01(-10.0), 0.0)

    def test_value_above_one_is_clamped_to_one(self) -> None:
        self.assertEqual(clamp01(12.0), 1.0)

    def test_boundaries_are_preserved(self) -> None:
        self.assertEqual(clamp01(0.0), 0.0)
        self.assertEqual(clamp01(1.0), 1.0)

class SmoothstepTests(unittest.TestCase):

    def test_below_lower_edge_returns_zero(self) -> None:
        self.assertEqual(smoothstep(0.2, 0.8, 0.1), 0.0)

    def test_above_upper_edge_returns_one(self) -> None:
        self.assertEqual(smoothstep(0.2, 0.8, 0.9), 1.0)

    def test_lower_edge_returns_zero(self) -> None:
        self.assertEqual(smoothstep(0.2, 0.8, 0.2), 0.0)

    def test_upper_edge_returns_one(self) -> None:
        self.assertEqual(smoothstep(0.2, 0.8, 0.8), 1.0)

    def test_midpoint_returns_half(self) -> None:
        self.assertAlmostEqual(smoothstep(0.0, 1.0, 0.5), 0.5)

    def test_equal_edges_behave_like_step(self) -> None:
        self.assertEqual(smoothstep(0.5, 0.5, 0.49), 0.0)
        self.assertEqual(smoothstep(0.5, 0.5, 0.5), 1.0)
        self.assertEqual(smoothstep(0.5, 0.5, 0.9), 1.0)

    def test_reversed_edges_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            smoothstep(0.8, 0.2, 0.5)

    def test_non_finite_values_are_rejected(self) -> None:
        cases = [(math.inf, 1.0, 0.5), (0.0, math.inf, 0.5), (0.0, 1.0, math.inf), (math.nan, 1.0, 0.5)]
        for edge0, edge1, value in cases:
            with self.subTest(edge0=edge0, edge1=edge1, value=value):
                with self.assertRaises(ValueError):
                    smoothstep(edge0, edge1, value)

class MaterialBlendConfigTests(unittest.TestCase):

    def test_default_configuration_is_valid(self) -> None:
        config = MaterialBlendConfig()
        config.validate()

    def test_min_facing_accepts_boundaries(self) -> None:
        for value in (0.0, 1.0):
            with self.subTest(value=value):
                config = default_config(min_facing=value)
                config.validate()

    def test_invalid_min_facing_is_rejected(self) -> None:
        for value in (-0.1, 1.1, math.inf, math.nan):
            with self.subTest(value=value):
                config = default_config(min_facing=value)
                with self.assertRaises(ValueError):
                    config.validate()

    def test_zero_facing_power_is_allowed(self) -> None:
        config = default_config(facing_power=0.0)
        config.validate()

    def test_negative_facing_power_is_rejected(self) -> None:
        config = default_config(facing_power=-1.0)
        with self.assertRaises(ValueError):
            config.validate()

    def test_relative_cutoff_accepts_boundaries(self) -> None:
        for value in (0.0, 1.0):
            with self.subTest(value=value):
                config = default_config(relative_score_cutoff=value)
                config.validate()

    def test_invalid_relative_cutoff_is_rejected(self) -> None:
        for value in (-0.01, 1.01, math.inf, math.nan):
            with self.subTest(value=value):
                config = default_config(relative_score_cutoff=value)
                with self.assertRaises(ValueError):
                    config.validate()

    def test_max_contributors_must_be_positive(self) -> None:
        for value in (0, -1, -50):
            with self.subTest(value=value):
                config = default_config(max_contributors=value)
                with self.assertRaises(ValueError):
                    config.validate()

    def test_weight_power_must_be_positive(self) -> None:
        for value in (0.0, -1.0, math.inf, math.nan):
            with self.subTest(value=value):
                config = default_config(weight_power=value)
                with self.assertRaises(ValueError):
                    config.validate()

class CandidateValidationTests(unittest.TestCase):

    def test_valid_candidate_passes(self) -> None:
        candidate = make_candidate()
        candidate.validate()

    def test_negative_base_weight_is_rejected(self) -> None:
        candidate = make_candidate(base_weight=-1.0)
        with self.assertRaises(ValueError):
            candidate.validate()

    def test_non_finite_values_are_rejected(self) -> None:
        candidates = [make_candidate(red=math.inf), make_candidate(green=math.nan), make_candidate(blue=math.inf), make_candidate(alpha=math.nan), make_candidate(base_weight=math.inf), make_candidate(facing=math.nan)]
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    candidate.validate()

    def test_color_property_clamps_channels(self) -> None:
        candidate = make_candidate(red=-1.0, green=0.5, blue=2.0, alpha=1.5)
        self.assertEqual(candidate.color, (0.0, 0.5, 1.0, 1.0))
