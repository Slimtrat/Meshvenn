from __future__ import annotations

import math
import unittest

from core.canonical_rig import MeshBounds, fit_canonical_biped
from core.rig_skinning import regional_fallback_weights


class RegionalFallbackSkinningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bounds = MeshBounds((-.75, -.2, 0), (.75, .2, 2))
        self.bones = fit_canonical_biped(self.bounds)

    def weights(self, point, *, bounds=None, bones=None, max_influences=4):
        return regional_fallback_weights(
            point,
            self.bones if bones is None else bones,
            self.bounds if bounds is None else bounds,
            max_influences=max_influences,
        )

    def test_grid_is_finite_normalized_bounded_and_deterministic(self) -> None:
        for x in (-.75, -.5, -.25, 0, .25, .5, .75):
            for y in (-.2, 0, .2):
                for z in (0, .4, .8, 1, 1.2, 1.5, 2):
                    point = (x, y, z)
                    weights = self.weights(point)
                    self.assertTrue(1 <= len(weights) <= 4, point)
                    self.assertAlmostEqual(sum(weights.values()), 1, places=12)
                    self.assertTrue(all(math.isfinite(value) and value > 0 for value in weights.values()))
                    self.assertEqual(weights, self.weights(point, bones=self.bones[::-1]))
                    self.assertNotIn("root", weights)

    def test_opposite_side_limbs_are_excluded_away_from_centerline(self) -> None:
        for x in (.12, .3, .65):
            for z in (.3, .9, 1.4):
                left = self.weights((x, 0, z))
                right = self.weights((-x, 0, z))
                self.assertFalse(any(name.endswith(".R") for name in left), left)
                self.assertFalse(any(name.endswith(".L") for name in right), right)

    def test_torso_does_not_receive_thigh_or_arm_weights(self) -> None:
        for x in (-.2, -.1, 0, .1, .2):
            for z in (1.2, 1.35, 1.5):
                weights = self.weights((x, 0, z))
                self.assertTrue(set(weights).issubset({"pelvis", "spine", "chest", "neck", "head"}), weights)

    def test_outer_limb_vertices_use_expected_region(self) -> None:
        arm = self.weights((.62, 0, 1.1))
        self.assertGreater(sum(value for name, value in arm.items() if name.endswith(".L")), .9)
        self.assertIn("forearm.L", arm)
        leg = self.weights((-.255, 0, .35))
        self.assertGreater(sum(value for name, value in leg.items() if name.endswith(".R")), .9)
        self.assertIn("shin.R", leg)

    def test_shoulder_and_hip_transitions_are_continuous(self) -> None:
        pairs = (
            ((.269, 0, 1.46), (.271, 0, 1.46)),
            ((.23, 0, 1.098), (.23, 0, 1.1)),
            ((.15, 0, 1.038), (.15, 0, 1.04)),
        )
        for first, second in pairs:
            a, b = self.weights(first), self.weights(second)
            change = sum(abs(a.get(name, 0) - b.get(name, 0)) for name in set(a) | set(b))
            self.assertLess(change, .10, (first, second, a, b))

    def test_handles_stylized_bounds_and_uniform_rescaling(self) -> None:
        for bounds in (
            MeshBounds((-3, -.02, 0), (3, .02, .4)),
            MeshBounds((-.05, -.2, 0), (.05, .2, 3)),
        ):
            bones = fit_canonical_biped(bounds)
            for name in ("forearm.L", "thigh.R", "head"):
                bone = next(item for item in bones if item.name == name)
                midpoint = tuple((a + b) / 2 for a, b in zip(bone.head, bone.tail))
                weights = self.weights(midpoint, bounds=bounds, bones=bones)
                self.assertAlmostEqual(sum(weights.values()), 1)
                self.assertIn(name, weights)
        point = (.45, .05, 1.16)
        baseline = self.weights(point)
        scaled = MeshBounds(tuple(v * 1000 for v in self.bounds.minimum),
                            tuple(v * 1000 for v in self.bounds.maximum))
        rescaled = self.weights(tuple(v * 1000 for v in point),
                                bounds=scaled, bones=fit_canonical_biped(scaled))
        self.assertEqual(set(baseline), set(rescaled))
        for name in baseline:
            self.assertAlmostEqual(baseline[name], rescaled[name], places=12)

    def test_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError):
            self.weights((0, 0, 1), max_influences=0)
        with self.assertRaises(ValueError):
            self.weights((math.nan, 0, 1))
        with self.assertRaises(ValueError):
            self.weights((0, 0, 3))
        with self.assertRaises(ValueError):
            self.weights((0, 0, 1), bones=self.bones[:-1])
        with self.assertRaises(ValueError):
            self.weights((0, 0, 1), bones=(*self.bones, self.bones[-1]))


if __name__ == "__main__":
    unittest.main()
