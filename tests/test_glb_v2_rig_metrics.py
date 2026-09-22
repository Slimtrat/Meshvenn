"""Pure checks for rig landmark and skin-weight score semantics."""

from __future__ import annotations

import unittest

from scripts.glb_v2_rig_metrics import RIGGED_FIGURE_LANDMARKS, landmark_summary, skin_weight_summary


class GLBV2RigMetricTests(unittest.TestCase):
    def test_landmarks_measure_error_in_model_heights(self) -> None:
        reference = {name: (0.0, 0.0, 0.0) for name in RIGGED_FIGURE_LANDMARKS.values()}
        generated = {name: (0.0, 0.0, 0.2) for name in RIGGED_FIGURE_LANDMARKS}
        report = landmark_summary(reference, generated, 2.0)
        self.assertEqual(report["landmark_count"], 17)
        self.assertAlmostEqual(report["mean_error_in_heights"], 0.1)
        self.assertAlmostEqual(report["max_error_in_heights"], 0.1)

    def test_missing_landmark_fails(self) -> None:
        with self.assertRaises(ValueError):
            landmark_summary({}, {}, 2.0)

    def test_skin_coverage_and_normalization_are_independent(self) -> None:
        report = skin_weight_summary([[0.5, 0.5], [1.0], []])
        self.assertEqual(report["weighted_fraction"], 2 / 3)
        self.assertEqual(report["unweighted_vertices"], 1)
        self.assertEqual(report["max_influences_per_vertex"], 2)
        self.assertEqual(report["max_weight_sum_error"], 0.0)
        self.assertAlmostEqual(skin_weight_summary([[0.4, 0.4]])["max_weight_sum_error"], 0.2)

    def test_invalid_weights_fail(self) -> None:
        with self.assertRaises(ValueError):
            skin_weight_summary([[1.0, -0.1]])
        with self.assertRaises(ValueError):
            skin_weight_summary([[float("nan")]])

    def test_empty_mesh_fails(self) -> None:
        with self.assertRaises(ValueError):
            skin_weight_summary([])


if __name__ == "__main__":
    unittest.main()
