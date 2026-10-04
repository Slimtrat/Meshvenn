"""Lower-body observations must use geometry, not fixed template heights."""

from __future__ import annotations

import math
import random
import unittest
from unittest.mock import patch

from core.canonical_rig import bounds_from_vertices
from core.canonical_rig_v2 import fit_canonical_biped_v2
from core.rig_lower_body import fit_lower_body


def lower_body_mesh(*, knee_z=.26, crotch=.45, shaped=True, diagonal=0, right_knee_z=None):
    vertices, triangles = [], []

    def loft(rings):
        start = len(vertices)
        for z, cx, cy, rx, ry in rings:
            vertices.extend(((cx-rx, cy-ry, z), (cx+rx, cy-ry, z),
                             (cx+rx, cy+ry, z), (cx-rx, cy+ry, z)))
        quads = [tuple(start + i for i in (3, 2, 1, 0)),
                 tuple(start + 4*(len(rings)-1) + i for i in range(4))]
        for ring in range(len(rings)-1):
            for i in range(4):
                quads.append((start+4*ring+i, start+4*ring+(i+1)%4,
                              start+4*(ring+1)+(i+1)%4, start+4*(ring+1)+i))
        for quad in quads:
            a,b,c,d = quad[diagonal:] + quad[:diagonal]
            triangles.extend(((a,b,c), (a,c,d)))

    for side in (-1, 1):
        knee = right_knee_z if side == -1 and right_knee_z is not None else knee_z
        profile = ((0, .03, .07), (.02, .03, .07), (.055, .025, .018),
                   (.13, .03, .025), (knee-.065, .035, .034),
                   (knee, .022, .021), (knee+.065, .035, .039),
                   (crotch+.01, .035, .043))
        loft([(z, side*.065, 0, rx if shaped else .03, ry if shaped else .03)
              for z,rx,ry in profile])
    loft([(crotch, 0, 0, .12, .06), (1, 0, 0, .12, .06)])
    return vertices, triangles


def measure(vertices, triangles):
    return fit_lower_body(vertices, triangles, bounds_from_vertices(vertices))


class LowerBodyFitTests(unittest.TestCase):
    def test_tracks_knee_height_and_derives_hip_from_observed_links(self):
        for knee, crotch in ((.23, .43), (.31, .54)):
            with self.subTest(knee=knee):
                points, triangles = lower_body_mesh(knee_z=knee, crotch=crotch)
                fit = measure(points, triangles)
                for side, leg in (("L",fit.left), ("R",fit.right)):
                    self.assertIsNotNone(leg.hip)
                    self.assertAlmostEqual(leg.knee[2], knee, delta=.01)
                    self.assertAlmostEqual(leg.ankle[2], .055, delta=.015)
                    self.assertAlmostEqual(leg.hip[2], leg.knee[2]+.95*(leg.knee[2]-leg.ankle[2]))
                    self.assertEqual(fit.evidence["legs"][side]["hip_method"], "observed-knee-ankle-length-prior")

    def test_missing_topology_is_an_explicit_fallback(self):
        points, _ = lower_body_mesh()
        fit = measure(points, None)
        self.assertIsNone(fit.left.hip)
        self.assertEqual(fit.evidence["fallback_reason"], "triangle-topology-unavailable")

    def test_featureless_legs_do_not_claim_joint_observations(self):
        points, triangles = lower_body_mesh(shaped=False)
        fit = measure(points, triangles)
        self.assertIsNone(fit.left.ankle)
        self.assertIsNone(fit.right.hip)
        self.assertEqual(fit.evidence["legs"]["L"]["fallback_reason"], "no-ankle-narrowing")

    def test_open_sections_are_not_used_as_closed_limb_envelopes(self):
        points, triangles = lower_body_mesh()
        triangles = [face for face in triangles if not all(points[i][0] > 0 for i in face)]
        fit = measure(points, triangles)
        self.assertIsNone(fit.left.hip)
        self.assertIsNone(fit.right.hip)

    def test_seams_duplicate_faces_and_face_order_do_not_change_fit(self):
        points, triangles = lower_body_mesh()
        expected = measure(points, triangles)
        split = [points[i] for face in triangles for i in face]
        split_faces = [tuple(range(i, i+3)) for i in range(0,len(split),3)]
        random.Random(1).shuffle(split_faces)
        actual = measure(split, split_faces + split_faces)
        self.assertEqual(expected, actual)

    def test_triangulation_diagonal_does_not_change_observed_heights(self):
        points, first = lower_body_mesh()
        other, second = lower_body_mesh(diagonal=1)
        a,b = measure(points, first), measure(other, second)
        for leg_a, leg_b in ((a.left,b.left), (a.right,b.right)):
            for joint in ("hip","knee","ankle"):
                self.assertLess(math.dist(getattr(leg_a,joint),getattr(leg_b,joint)),1e-8)

    def test_translation_and_scale_do_not_change_normalized_observations(self):
        points, triangles = lower_body_mesh()
        fit = measure(points, triangles)
        moved = [(2+3*x, -4+3*y, 7+3*z) for x,y,z in points]
        actual = measure(moved, triangles)
        for before,after in ((fit.left,actual.left),(fit.right,actual.right)):
            for joint in ("hip","knee","ankle"):
                expected = tuple(o+3*v for v,o in zip(getattr(before,joint),(2,-4,7)))
                self.assertLess(math.dist(expected,getattr(after,joint)),1e-8)

    def test_canonical_fitter_consumes_topology_and_keeps_semantics(self):
        points, triangles = lower_body_mesh(knee_z=.31,crotch=.54)
        original,_ = fit_canonical_biped_v2(points)
        bones,report = fit_canonical_biped_v2(points,triangles=triangles)
        self.assertEqual({b.name for b in bones},{b.name for b in original})
        by_name = {b.name:b for b in bones}
        self.assertGreater(by_name["shin.L"].head[2], .30)
        self.assertGreater(by_name["pelvis"].head[2], .50)
        self.assertEqual(report.as_dict()["schema_version"],2)

    def test_surface_cues_within_resolution_do_not_move_stable_anchors(self):
        points, triangles = lower_body_mesh(knee_z=.245)
        baseline,_ = fit_canonical_biped_v2(points)
        bones,report = fit_canonical_biped_v2(points,triangles=triangles)
        for before,after in zip(baseline,bones):
            if before.name.startswith(("thigh.","shin.","foot.")):
                self.assertEqual(before.head,after.head)
        self.assertEqual(report.lower_body["applied_anchors"]["L"]["hip"],
                         "canonical-within-observation-resolution")

    def test_conflicting_bilateral_hip_estimates_fall_back_without_hiding_knees(self):
        points, triangles = lower_body_mesh(knee_z=.23,right_knee_z=.29)
        fit = measure(points,triangles)
        self.assertIsNone(fit.left.hip)
        self.assertIsNone(fit.right.hip)
        self.assertIsNotNone(fit.left.knee)
        self.assertIsNotNone(fit.right.knee)
        for report in fit.evidence["legs"].values():
            self.assertEqual(report["hip_method"],"canonical-prior")
            self.assertNotIn("hip_height_in_heights",report)

    def test_hip_prior_inconsistent_with_surface_remains_explicit(self):
        points, triangles = lower_body_mesh(knee_z=.32,crotch=.55)
        fit = measure(points,triangles)
        self.assertIsNone(fit.left.hip)
        self.assertIsNotNone(fit.left.knee)
        self.assertEqual(fit.evidence["legs"]["L"]["fallback_reason"],
                         "hip-length-prior-inconsistent-with-surface")

    def test_ankle_observation_does_not_fabricate_a_knee_on_straight_legs(self):
        points, triangles = lower_body_mesh()
        for index,(x,y,z) in enumerate(points[:64]):
            if z > .03:
                cx = .065 if x > 0 else -.065
                points[index] = (cx + (.03 if x > cx else -.03),
                                 .025 if y > 0 else -.025,z)
        fit = measure(points,triangles)
        self.assertIsNotNone(fit.left.ankle)
        self.assertIsNone(fit.left.knee)
        self.assertIsNone(fit.left.hip)
        self.assertEqual(fit.evidence["legs"]["L"]["fallback_reason"],"no-knee-cue")

    def test_invalid_triangle_indices_and_nonfinite_points_are_rejected(self):
        points, triangles = lower_body_mesh()
        for face in ((-1,1,2),(0,1,len(points)),(0,1),(0,0,2),(True,1,2),(0,1,2.0)):
            with self.subTest(face=face), self.assertRaises(ValueError):
                measure(points,[face])
        with self.assertRaises(ValueError):
            fit_lower_body([(0,float("nan"),0)], triangles,bounds_from_vertices(points))

    def test_extrapolated_hip_outside_the_body_falls_back(self):
        points, triangles = lower_body_mesh()
        with patch("core.rig_lower_body._center_at",return_value=(.30,0,.46)):
            fit = measure(points,triangles)
        self.assertIsNone(fit.left.hip)
        self.assertIsNotNone(fit.left.knee)
        self.assertEqual(fit.evidence["legs"]["L"]["fallback_reason"],"hip-center-extrapolation-outside-body")


if __name__ == "__main__":
    unittest.main()
