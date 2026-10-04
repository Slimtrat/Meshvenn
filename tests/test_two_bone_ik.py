import math
import random
import unittest

from core.two_bone_ik import solve_two_bone
from core.motion_contacts import contact_envelope, blended_contacts


class TwoBoneIKTests(unittest.TestCase):
    def test_reachable_goal_preserves_both_link_lengths_and_bend_side(self):
        solved = solve_two_bone((0,0,0), (1,0,0), (1,1,0), (.5,1,0))
        self.assertAlmostEqual(math.dist((0,0,0), solved.knee), 1)
        self.assertAlmostEqual(math.dist(solved.knee, solved.ankle), 1)
        self.assertLess(solved.reach_error, 1e-12)
        self.assertGreater(solved.knee[0], 0)

    def test_unreachable_far_goal_is_reported_not_stretched(self):
        solved = solve_two_bone((0,0,0), (0,0,-1), (0,0,-2), (0,0,-4))
        self.assertAlmostEqual(math.dist((0,0,0), solved.knee), 1)
        self.assertAlmostEqual(math.dist(solved.knee, solved.ankle), 1)
        self.assertGreater(solved.reach_error, 2)

    def test_folded_and_zero_distance_goals_are_finite(self):
        for ankle, goal in (((0,0,-2),(0,0,0)), ((0,0,0),(0,0,0)), ((0,0,-3),(0,0,-.01))):
            solved = solve_two_bone((0,0,0), (0,0,-1), ankle, goal)
            self.assertTrue(all(math.isfinite(v) for v in (*solved.knee,*solved.ankle,solved.reach_error)))
            self.assertAlmostEqual(math.dist((0,0,0), solved.knee), 1)
            self.assertAlmostEqual(math.dist(solved.knee, solved.ankle), math.dist((0,0,-1),ankle))

    def test_parallel_or_zero_poles_have_deterministic_fallbacks(self):
        for pole in ((0,0,-1),(0,0,0)):
            solved = solve_two_bone((0,0,0),(0,0,-1),(0,0,-2),(0,0,-1),pole=pole)
            self.assertEqual(solved,solve_two_bone((0,0,0),(0,0,-1),(0,0,-2),(0,0,-1),pole=pole))
            self.assertAlmostEqual(math.dist((0,0,0),solved.knee),1)

    def test_scale_and_translation_equivariance(self):
        original = ((0,0,0),(1,0,-1),(0,0,-2),(.2,.3,-1))
        solved = solve_two_bone(*original)
        for scale in (.001, 2, 10000):
            offset = (3,-4,2)
            points = [tuple(v*scale+o for v,o in zip(p,offset)) for p in original]
            other = solve_two_bone(*points)
            self.assertLess(math.dist(other.knee,tuple(v*scale+o for v,o in zip(solved.knee,offset))),scale*1e-8)
            self.assertAlmostEqual(other.reach_error,solved.reach_error*scale,places=8)

    def test_large_representable_coordinates_do_not_overflow_squares(self):
        solved = solve_two_bone((0,0,0),(1e200,0,0),(1e200,1e200,0),(.5e200,1e200,0))
        self.assertTrue(all(math.isfinite(v) for v in (*solved.knee,*solved.ankle)))
        self.assertAlmostEqual(math.dist((0,0,0),solved.knee)/1e200,1)

    def test_random_goals_never_change_lengths(self):
        rng = random.Random(42)
        for _ in range(300):
            points = [tuple(rng.uniform(-2,2) for _ in range(3)) for _ in range(4)]
            solved = solve_two_bone(*points)
            self.assertAlmostEqual(math.dist(points[0],solved.knee),math.dist(points[0],points[1]),places=6)
            self.assertAlmostEqual(math.dist(solved.knee,solved.ankle),math.dist(points[1],points[2]),places=6)

    def test_invalid_points_and_degenerate_links_fail(self):
        for bad in ((1,2),(math.nan,0,0),(math.inf,0,0),(True,0,0)):
            with self.assertRaises(ValueError): solve_two_bone(bad,(1,0,0),(2,0,0),(1,1,0))
        for points in (((0,0,0),(0,0,0),(1,0,0)),((0,0,0),(1,0,0),(1,0,0))):
            with self.assertRaises(ValueError): solve_two_bone(*points,(0,1,0))
        with self.assertRaises(ValueError):
            solve_two_bone((0,0,0),(1,0,0),(1.000000001,0,0),(.5,0,0))

    def test_contact_envelope_full_inside_smooth_outside_and_zero_without_windows(self):
        runs = (list(range(10,21)), list(range(30,41)))
        self.assertEqual(contact_envelope(0,(),60),(None,0))
        for index in (10,15,20): self.assertEqual(contact_envelope(index,runs,60),(runs[0],1))
        self.assertEqual(contact_envelope(5,runs,60),(None,0))
        self.assertGreater(contact_envelope(9,runs,60)[1],contact_envelope(8,runs,60)[1])
        self.assertEqual(contact_envelope(25,runs,60),(None,0))

    def test_overlapping_halos_crossfade_without_a_nearest_window_jump(self):
        runs = (list(range(0,11)), list(range(14,21)))
        for boundary in (10,14):
            expected = 0 if boundary == 10 else 1
            for point in (boundary-1e-5,boundary,boundary+1e-5):
                blends,strength = blended_contacts(point,runs,60)
                position = sum(weight*(run is runs[1]) for run,weight in blends)
                self.assertAlmostEqual(position,expected,places=8)
                self.assertAlmostEqual(strength,1,places=8)
        blends,strength = blended_contacts(12,runs,60)
        self.assertAlmostEqual(sum(weight for _,weight in blends),1)
        self.assertAlmostEqual(blends[1][1],.5)
        self.assertGreater(strength,0)
        self.assertLess(strength,1)

    def test_large_contact_gap_has_no_artificial_middle_support(self):
        self.assertEqual(blended_contacts(25,(list(range(0,11)),list(range(40,51))),60),((),0))


if __name__ == "__main__": unittest.main()
