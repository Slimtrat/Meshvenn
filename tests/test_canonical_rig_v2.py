"""Pure contract and invariance tests for Canonical Biped V2."""

from __future__ import annotations

import random
import unittest

from core.canonical_rig_v2 import fit_canonical_biped_v2


EXPECTED = {
    "root", "pelvis", "spine", "chest", "neck", "head",
    *(f"{part}.{side}" for side in ("L", "R") for part in (
        "upper_arm", "forearm", "hand", "thigh", "shin", "foot"
    )),
}


def biped_points(*, wrist_z: float = 0.59) -> list[tuple[float, float, float]]:
    points = []
    for z_index in range(21):
        z = z_index / 20
        half_width = 0.10 if z > 0.42 else 0.075
        for x in (-half_width, 0.0, half_width):
            points.extend(((x, -0.06, z), (x, 0.06, z)))
    for side in (-1, 1):
        for index in range(18):
            fraction = index / 17
            x = side * (0.23 + 0.17 * fraction)
            z = 0.741 + (wrist_z - 0.741) * fraction
            points.extend(((x, -0.025, z), (x, 0.025, z)))
        for z in (0.08, 0.16, 0.24, 0.32, 0.40):
            points.extend(((side * 0.052, -0.04, z), (side * 0.052, 0.04, z)))
    return points


def normalized_bones(points):
    bones, _ = fit_canonical_biped_v2(points)
    low = min(point[2] for point in points)
    height = max(point[2] for point in points) - low
    center_x = (min(point[0] for point in points) + max(point[0] for point in points)) * 0.5
    return {
        bone.name: tuple(round((value - origin) / height, 8) for value, origin in zip(
            bone.head, (center_x, 0.0, low)
        ))
        for bone in bones
    }


class CanonicalRigV2Tests(unittest.TestCase):
    def test_produces_stable_canonical_hierarchy(self) -> None:
        bones, report = fit_canonical_biped_v2(biped_points())
        self.assertEqual({bone.name for bone in bones}, EXPECTED)
        self.assertEqual(len(bones), 18)
        self.assertEqual(report.arm_pose, "a-pose")
        self.assertGreater(report.confidence, 0.8)
        self.assertAlmostEqual(next(b for b in bones if b.name == "upper_arm.L").head[0], 0.06, places=2)

    def test_arm_envelope_tracks_a_and_t_pose(self) -> None:
        a_bones, a_report = fit_canonical_biped_v2(biped_points(wrist_z=0.58))
        t_bones, t_report = fit_canonical_biped_v2(biped_points(wrist_z=0.74))
        a_wrist = next(b for b in a_bones if b.name == "hand.L").head[2]
        t_wrist = next(b for b in t_bones if b.name == "hand.L").head[2]
        self.assertEqual(a_report.arm_pose, "a-pose")
        self.assertEqual(t_report.arm_pose, "t-pose")
        self.assertGreater(t_wrist, a_wrist + 0.06)

    def test_is_invariant_to_order_translation_and_scale(self) -> None:
        points = biped_points()
        expected = normalized_bones(points)
        random.Random(2026).shuffle(points)
        transformed = [(10 + 3 * x, -7 + 3 * y, 4 + 3 * z) for x, y, z in points]
        actual = normalized_bones(transformed)
        for name in EXPECTED:
            self.assertEqual(expected[name][0], actual[name][0])
            self.assertEqual(expected[name][2], actual[name][2])

    def test_rejects_empty_and_nonfinite_geometry(self) -> None:
        with self.assertRaises(ValueError):
            fit_canonical_biped_v2([])
        with self.assertRaises(ValueError):
            fit_canonical_biped_v2([(0, 0, 0), (1, float("nan"), 2)])


if __name__ == "__main__":
    unittest.main()
