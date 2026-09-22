from __future__ import annotations

import json
import math
import unittest
from dataclasses import FrozenInstanceError

from core.canonical_rig import MeshBounds
from core.rig_quality import RigGeometryAssessment, assess_biped_geometry


class RigQualityTests(unittest.TestCase):
    def test_stylized_symmetric_biped_has_balanced_measures(self) -> None:
        bounds = MeshBounds((-1, -0.3, 0), (1, 0.3, 2.4))
        points = (
            (side * distance, 0, height)
            for height in (0.0, 0.3, 0.8, 1.2, 1.7, 2.4)
            for distance in (0.15, 0.55, 1.0)
            for side in (-1, 1)
        )
        result = assess_biped_geometry(points, bounds)
        self.assertIsInstance(result, RigGeometryAssessment)
        self.assertEqual(result.vertex_count, 36)
        self.assertAlmostEqual(result.height_to_width, 1.2)
        self.assertEqual(result.left_vertex_count, result.right_vertex_count)
        self.assertAlmostEqual(result.left_right_envelope_imbalance, 0)
        self.assertAlmostEqual(result.bilateral_vertex_coverage, 1)
        self.assertEqual(result.warnings, ())
        with self.assertRaises(FrozenInstanceError):
            result.vertex_count = 0

        wire = result.as_dict()
        self.assertEqual(wire["schema_version"], 1)
        self.assertEqual(wire["warnings"], [])
        self.assertNotIn("anatomy_score", wire)
        self.assertEqual(json.loads(json.dumps(wire, allow_nan=False)), wire)

    def test_envelope_imbalance_ignores_single_extremal_counterexample(self) -> None:
        bounds = MeshBounds((-1, -0.2, 0), (1, 0.2, 2))
        left = [(0.8 + index * 0.02, 0, 1) for index in range(10)]
        right = [(-0.08 - index * 0.002, 0, 1) for index in range(9)] + [(-1, 0, 1)]
        result = assess_biped_geometry(left + right, bounds)
        self.assertGreater(result.left_right_envelope_imbalance, 0.45)
        self.assertEqual(result.bilateral_vertex_coverage, 1)
        self.assertEqual(result.warnings, ("left_right_envelope_imbalance",))

    def test_unilateral_coverage_warns_without_rejecting(self) -> None:
        bounds = MeshBounds((-1, -0.2, 0), (1, 0.2, 2))
        points = [(0.5, 0, index / 10) for index in range(20)] + [(-1, 0, 1)]
        result = assess_biped_geometry(points, bounds)
        self.assertLess(result.bilateral_vertex_coverage, 0.30)
        self.assertIn("low_bilateral_vertex_coverage", result.warnings)

    def test_extreme_aspect_ratios_are_warnings_not_errors(self) -> None:
        squat = assess_biped_geometry(
            [(-1, 0, 0), (1, 0, 0.4)], MeshBounds((-1, -0.1, 0), (1, 0.1, 0.4))
        )
        tall = assess_biped_geometry(
            [(-0.1, 0, 0), (0.1, 0, 2)], MeshBounds((-0.1, -0.1, 0), (0.1, 0.1, 2))
        )
        self.assertIn("low_height_to_width", squat.warnings)
        self.assertIn("high_height_to_width", tall.warnings)

    def test_invalid_or_empty_vertices_rejected(self) -> None:
        bounds = MeshBounds((-1, -0.2, 0), (1, 0.2, 2))
        for points in ((), ((0, 0),), ((0, math.nan, 1),), ((0, 0, math.inf),)):
            with self.subTest(points=points), self.assertRaises(ValueError):
                assess_biped_geometry(points, bounds)
        with self.assertRaises(TypeError):
            assess_biped_geometry(((0, 0, 0),), None)  # type: ignore[arg-type]

    def test_centerline_vertices_do_not_artificially_balance_sides(self) -> None:
        bounds = MeshBounds((-1, -0.2, 0), (1, 0.2, 2))
        points = [(0, 0, index / 10) for index in range(20)] + [(1, 0, 1), (-1, 0, 1)]
        result = assess_biped_geometry(points, bounds)
        self.assertEqual(result.left_vertex_count, 1)
        self.assertEqual(result.right_vertex_count, 1)
        self.assertEqual(result.bilateral_vertex_coverage, 1)
        self.assertEqual(result.warnings, ())


if __name__ == "__main__":
    unittest.main()
