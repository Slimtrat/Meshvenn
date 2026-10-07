"""Authored collars, bounded axial weights, seam safety and exact distal skin."""
import copy
import math
import random
import unittest

from core.canonical_rig import bounds_from_vertices, fit_canonical_biped
from core.rig_head_envelope import HeadEnvelope
from core.rig_owned_skin import refine_owned_weights


def authored_surface():
    points, faces, roles, index = [], [], [], {}
    for iz in range(40):
        z = (iz+.5)/40
        for ix in range(-20, 20):
            x = (ix+.5)/40
            role = None
            if .60 <= z < .675 and abs(x) >= .125:
                role = "left-arm" if x > 0 else "right-arm"
            elif z < .40 and .025 <= abs(x) < .125:
                role = "left-leg" if x > 0 else "right-leg"
            elif (.40 <= z < .675 and abs(x) < .125
                  or .675 <= z < .775 and abs(x) < .05
                  or .775 <= z and abs(x) < .15):
                role = "body-core"
            if role is None:
                continue
            face = []
            for a, b in ((ix, iz), (ix+1, iz), (ix+1, iz+1), (ix, iz+1)):
                if (a, b) not in index:
                    index[a, b] = len(points)
                    points.append((a/40, .02*a/40+.015*math.cos(b/40), b/40))
                face.append(index[a, b])
            faces.append(tuple(face))
            roles.append(role)
    bones = fit_canonical_biped(bounds_from_vertices(points))
    weights = [{"pelvis": .4, "upper_arm.L": .3, "forearm.L": .3} for _ in points]
    return points, faces, roles, weights, bones, HeadEnvelope(.68, .765, .72, .9, 8)


class OwnedSkinTests(unittest.TestCase):
    def test_axial_shell_has_no_distant_limb_influences_and_head_is_rigid(self):
        inputs = authored_surface()
        original = copy.deepcopy(inputs[:4])
        rows, report = refine_owned_weights(*inputs)
        self.assertGreater(report["changed_vertex_count"], 100)
        self.assertGreater(report["unchanged_distal_vertex_count"], 50)
        for p, row in zip(inputs[0], rows):
            self.assertLessEqual(len(row), 4)
            self.assertAlmostEqual(sum(row.values()), 1.)
            self.assertTrue(all(v > 0 for v in row.values()))
            if .50 < p[2] < .57 and abs(p[0]) < .04:
                self.assertTrue(set(row) <= {"pelvis", "spine"})
            if p[2] >= .80:
                self.assertEqual(row, {"head": 1.})
        self.assertEqual(inputs[:4], original)

    def test_distal_limb_weights_are_bit_exact_not_renormalized(self):
        inputs = authored_surface()
        rows, _ = refine_owned_weights(*inputs)
        for p, before, after in zip(inputs[0], inputs[3], rows):
            if p[2] < .20 or abs(p[0]) > .30:
                self.assertEqual(after, before)
                self.assertEqual(list(after), list(before))

    def test_scale_translation_face_order_and_seam_duplication_preserve_edit(self):
        points, faces, roles, weights, bones, envelope = authored_surface()
        expected, _ = refine_owned_weights(points, faces, roles, weights, bones, envelope)
        order = list(range(len(faces)))
        random.Random(7).shuffle(order)
        actual, _ = refine_owned_weights(points, [faces[i] for i in order], [roles[i] for i in order], weights, bones, envelope)
        self.assertEqual(actual, expected)
        split = [points[i] for face in faces for i in face]
        split_weights = [weights[i] for face in faces for i in face]
        split_faces = [tuple(range(i, i+4)) for i in range(0, len(split), 4)]
        actual, _ = refine_owned_weights(split, split_faces, roles, split_weights, bones, envelope)
        self.assertEqual(actual, [expected[i] for face in faces for i in face])
        from dataclasses import replace
        for scale in (.01, 500.):
            def moved(p):
                return tuple(shift+scale*v for shift, v in zip((2, -3, 7), p))
            transformed = [replace(b, head=moved(b.head), tail=moved(b.tail)) for b in bones]
            profile = replace(envelope, start_z=7+scale*envelope.start_z,
                              end_z=7+scale*envelope.end_z, neck_z=7+scale*envelope.neck_z)
            actual, _ = refine_owned_weights([moved(p) for p in points], faces, roles, weights, transformed, profile)
            for a, b in zip(actual, expected):
                self.assertEqual(set(a), set(b))
                for k in a:
                    self.assertAlmostEqual(a[k], b[k], places=9)

    def test_missing_ownership_or_head_evidence_cannot_be_guessed(self):
        inputs = list(authored_surface())
        for field, replacement in ((2, ["body-core"]*len(inputs[1])), (5, None)):
            bad = inputs.copy()
            bad[field] = replacement
            with self.assertRaises(ValueError):
                refine_owned_weights(*bad)
        for width in (True, .001, .10, math.nan):
            with self.assertRaises(ValueError):
                refine_owned_weights(*inputs, collar_in_heights=width)

    def test_invalid_weights_and_contradictory_seams_fail_closed(self):
        for row in ({}, {"head": 2}, {"head": math.nan}, {"head": -1}, {"unknown": 1}):
            inputs = list(authored_surface())
            inputs[3][0] = row
            with self.assertRaises(ValueError):
                refine_owned_weights(*inputs)
        points, faces, roles, weights, bones, envelope = authored_surface()
        split = [points[i] for face in faces for i in face]
        split_weights = [weights[i].copy() for face in faces for i in face]
        from collections import Counter
        duplicate = next(p for p, count in Counter(split).items() if count > 1)
        split_weights[split.index(duplicate)] = {"head": 1.}
        with self.assertRaisesRegex(ValueError, "contradictory"):
            refine_owned_weights(split, [tuple(range(i, i+4)) for i in range(0, len(split), 4)],
                                 roles, split_weights, bones, envelope)

    def test_disconnected_limb_and_inverted_axial_anchors_fail_closed(self):
        from dataclasses import replace
        inputs = list(authored_surface())
        inputs[4] = [replace(b, head=(b.head[0], b.head[1], .1)) if b.name == "spine" else b for b in inputs[4]]
        with self.assertRaisesRegex(ValueError, "axial"):
            refine_owned_weights(*inputs)
        inputs = list(authored_surface())
        start = len(inputs[0])
        inputs[0] += [(2, 0, .61), (2.1, 0, .61), (2.1, .01, .65)]
        inputs[1].append((start, start+1, start+2))
        inputs[2].append("left-arm")
        inputs[3] += [{"hand.L": 1.}]*3
        with self.assertRaisesRegex(ValueError, "Disconnected"):
            refine_owned_weights(*inputs)


    def test_multiple_disjoint_attachment_interfaces_are_not_guessed(self):
        inputs = list(authored_surface())
        island = next(i for i, (face, role) in enumerate(zip(inputs[1], inputs[2]))
                      if role == "left-arm" and min(inputs[0][v][0] for v in face) > .3)
        inputs[2][island] = "body-core"
        with self.assertRaisesRegex(ValueError, "Disconnected source interface"):
            refine_owned_weights(*inputs)


if __name__ == "__main__":
    unittest.main()
