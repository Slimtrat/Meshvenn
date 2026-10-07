"""Head isolation evidence, safe fallbacks, invariance and bounded weights."""
import math
import random
import unittest

from core.canonical_rig import bounds_from_vertices
from core.rig_head_envelope import HeadEnvelope, isolate_head_weights, observe_head_envelope


def loft(*, neck=.70, constriction=True, diagonal=0):
    points, triangles = [], []
    rings = [(0, .11, .08), (neck-.09, .13, .08), (neck-.025, .04, .035),
             (neck+.025, .04, .035), (neck+.08, .15, .12), (1, .14, .11)]
    for z, rx, ry in rings:
        if not constriction:
            rx, ry = .13, .09
        points.extend(((-rx, -ry, z), (rx, -ry, z), (rx, ry, z), (-rx, ry, z)))
    for ring in range(len(rings)-1):
        for i in range(4):
            q = (ring*4+i, ring*4+(i+1)%4, (ring+1)*4+(i+1)%4, (ring+1)*4+i)
            a, b, c, d = q[diagonal:]+q[:diagonal]
            triangles.extend(((a, b, c), (a, c, d)))
    triangles.extend(((0, 2, 1), (0, 3, 2), (20, 21, 22), (20, 22, 23)))
    return points, triangles


def observe(points, faces):
    return observe_head_envelope(points, faces, bounds_from_vertices(points))


class HeadEnvelopeTests(unittest.TestCase):
    def test_tracks_observed_neck_not_template_height(self):
        for height in (.69, .81):
            points, faces = loft(neck=height)
            result = observe(points, faces)
            self.assertIsNotNone(result)
            self.assertLessEqual(abs(result.neck_z-height), .0251)
            self.assertGreater(result.contrast, .55)
            self.assertLess(result.start_z, height)
            self.assertGreater(result.end_z, height)

    def test_seams_duplicate_faces_density_and_face_order_do_not_change_observation(self):
        points, faces = loft()
        expected = observe(points, faces)
        split = [points[i] for face in faces for i in face]
        seams = [tuple(range(i, i+3)) for i in range(0, len(split), 3)]
        random.Random(1).shuffle(seams)
        self.assertEqual(expected, observe(split, seams+seams))
        self.assertEqual(expected, observe(*loft(diagonal=1)))

    def test_translation_and_scale_invariance(self):
        points, faces = loft()
        expected = observe(points, faces)
        for scale in (.001, 5, 1e6):
            moved = [(7+scale*x, -9+scale*y, 11+scale*z) for x, y, z in points]
            actual = observe(moved, faces)
            self.assertIsNotNone(actual)
            for name in ("start_z", "end_z", "neck_z"):
                self.assertAlmostEqual((getattr(actual, name)-11)/scale, getattr(expected, name), places=7)
            self.assertAlmostEqual(actual.contrast, expected.contrast, places=6)

    def test_missing_topology_featureless_open_and_disconnected_surfaces_fall_back(self):
        points, faces = loft()
        self.assertIsNone(observe(points, None))
        self.assertIsNone(observe(*loft(constriction=False)))
        self.assertIsNone(observe(points, [f for f in faces if not all(points[i][1] < 0 for i in f)]))
        self.assertIsNone(observe(points, [f for f in faces if not min(points[i][2] for i in f) < .7 < max(points[i][2] for i in f)]))

    def test_raised_appendage_does_not_become_head(self):
        points, faces = loft()
        self.assertIsNone(observe(points+[(.35, 0, .92)], faces))

    def test_rejects_nonfinite_and_invalid_topology(self):
        points, faces = loft()
        bounds = bounds_from_vertices(points)
        for bad in ([(-1, 0, 1)], [(True, 1, 2)], [(1, 1, 2)]):
            with self.assertRaises(ValueError):
                observe_head_envelope(points, bad, bounds)
        with self.assertRaises(ValueError):
            observe_head_envelope([(0, math.nan, 0)], faces, bounds)

    def test_shell_is_rigid_and_lower_body_weights_are_bit_exact(self):
        envelope = observe(*loft())
        old = {"upper_arm.L": .3, "chest": .4, "neck": .2, "head": .1}
        self.assertEqual(isolate_head_weights(old, .90, envelope), {"head": 1})
        self.assertEqual(isolate_head_weights(old, .45, envelope), old)
        self.assertEqual(isolate_head_weights(old, .9, None), old)
        self.assertEqual(isolate_head_weights(old, envelope.start_z, envelope), old)
        for i in range(101):
            z = envelope.start_z+(envelope.end_z-envelope.start_z)*i/100
            result = isolate_head_weights(old, z, envelope)
            self.assertLessEqual(len(result), 4)
            self.assertAlmostEqual(sum(result.values()), 1)
            self.assertTrue(all(v > 0 for v in result.values()))
            self.assertEqual(result, isolate_head_weights(dict(reversed(tuple(old.items()))), z, envelope))

    def test_neck_transition_is_continuous_and_deterministic_under_pruning(self):
        envelope = observe(*loft())
        old = {"upper_arm.L": .5, "forearm.L": .0001, "chest": .3, "neck": .1999}
        previous = old
        for i in range(1001):
            z = envelope.start_z+(envelope.end_z-envelope.start_z)*i/1000
            weights = isolate_head_weights(old, z, envelope)
            self.assertLess(sum(abs(weights.get(k, 0)-previous.get(k, 0)) for k in weights.keys() | previous.keys()), .02)
            previous = weights

    def test_invalid_weights_cannot_be_laundered_into_rigid_head(self):
        envelope = observe(*loft())
        for weights in ({}, {"head": math.nan}, {"head": 2}, {"head": -1}, {"": 1}):
            with self.assertRaises(ValueError):
                isolate_head_weights(weights, .9, envelope)
        with self.assertRaises(ValueError):
            isolate_head_weights({"head": 1}, .9, envelope, max_influences=True)
        with self.assertRaises(ValueError):
            HeadEnvelope(1, 0, .5, .9, 5)


if __name__ == "__main__":
    unittest.main()
