from pathlib import Path
import copy, math, sys, unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from meshvenn_humanoid.skinning import Segment, localize_arms


def bones(scale=1):
    return {
        f"{n}.{s}": Segment(tuple(scale * x for x in a), tuple(scale * x for x in b))
        for s, sign in (("L", 1), ("R", -1))
        for n, a, b in (
            ("upper_arm", (sign * 0.1, 0, 1), (sign * 0.4, 0, 1)),
            ("forearm", (sign * 0.4, 0, 1), (sign * 0.7, 0, 1)),
            ("hand", (sign * 0.7, 0, 1), (sign * 0.9, 0, 1)),
        )
    }


class SkinTests(unittest.TestCase):
    def test_parent_and_distal_links_are_rigid_outside_the_hinge(self):
        points = [(0.2, 0, 1), (0.55, 0, 1), (0.4, 0, 1), (-0.55, 0, 1)]
        old = [{"upper_arm.L": 0.5, "forearm.L": 0.5}] * 3 + [
            {"upper_arm.R": 0.5, "forearm.R": 0.5}
        ]
        result, _ = localize_arms(points, old, bones())
        self.assertEqual(result[0], {"upper_arm.L": 1.0})
        self.assertEqual(result[1], {"forearm.L": 1.0})
        self.assertAlmostEqual(result[2]["upper_arm.L"], 0.5)
        self.assertEqual(result[3], {"forearm.R": 1.0})

    def test_torso_attachment_keeps_its_axial_mass_but_not_child_influence(self):
        old = [{"chest": 0.6, "forearm.L": 0.2, "upper_arm.L": 0.2}]
        result, _ = localize_arms([(0, 0, 1)], old, bones())
        self.assertEqual(result, [{"chest": 0.6, "upper_arm.L": 0.4}])

    def test_legs_and_head_with_no_arm_influence_are_exact(self):
        old = [{"head": 1.0}, {"thigh.L": 0.7, "shin.L": 0.3}]
        self.assertEqual(
            localize_arms([(0, 0, 2), (0.1, 0, 0.4)], old, bones())[0], old
        )

    def test_distal_cleanup_removes_foreign_mass_without_reintroducing_opposite_arm(
        self,
    ):
        old = [{"forearm.L": 0.8, "upper_arm.R": 0.001, "chest": 0.199}]
        result, _ = localize_arms([(0.55, 0, 1)], old, bones())
        self.assertEqual(result, [{"forearm.L": 1.0}])

    def test_scale_invariance_source_immutability_and_four_weight_bound(self):
        points = [(0.36, 0.02, 1.0)]
        old = [{"upper_arm.L": 0.6, "forearm.L": 0.4}]
        saved = copy.deepcopy(old)
        a, _ = localize_arms(points, old, bones())
        b, _ = localize_arms([tuple(3 * x for x in p) for p in points], old, bones(3))
        for n in a[0]:
            self.assertAlmostEqual(a[0][n], b[0][n])
        self.assertEqual(old, saved)
        self.assertLessEqual(len(a[0]), 4)
        self.assertAlmostEqual(sum(a[0].values()), 1.0)

    def test_rejects_degenerate_frames_and_invalid_rows(self):
        with self.assertRaises(ValueError):
            Segment((0, 0, 0), (0, 0, 0))
        with self.assertRaises(ValueError):
            localize_arms([(0, 0, 1)], [{"head": 2.0}], bones())

    def test_radial_transition_uses_flexion_thickness_and_is_scale_invariant(self):
        points = []
        old = []
        for s, sign in (("L", 1), ("R", -1)):
            for y, z in ((-0.2, -0.04), (0.2, -0.04), (0.2, 0.04), (-0.2, 0.04)):
                points.append((sign * 0.4, y, 1 + z))
                old.append({"upper_arm." + s: 0.6, "forearm." + s: 0.4})
        a, report = localize_arms(points, old, bones(), radial_expansion=2.0)
        b, scaled = localize_arms(
            [tuple(3 * x for x in p) for p in points],
            old,
            bones(3),
            radial_expansion=2.0,
        )
        self.assertAlmostEqual(report["observed_elbow_radius"]["L"], 0.04)
        self.assertAlmostEqual(scaled["observed_elbow_radius"]["L"], 0.12)
        for left, right in zip(a, b):
            for n in left:
                self.assertAlmostEqual(left[n], right[n])
