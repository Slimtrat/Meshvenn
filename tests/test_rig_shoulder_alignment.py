"""Closed authored cut rings: deterministic centers and bounded native shifts."""
from collections import defaultdict
from dataclasses import replace
import random
import unittest

from core.canonical_rig import bounds_from_vertices, fit_canonical_biped
from core.rig_shoulder_alignment import observed_shoulder_centers, plan_shoulder_alignment
from tests.test_rig_owned_skin import authored_surface


def closed_surface():
    points, faces, roles, *_ = authored_surface()
    n = len(points)
    edges = defaultdict(list)
    for face, role in zip(faces,roles):
        for a,b in zip(face,(*face[1:],face[0])):
            edges[tuple(sorted((a,b)))].append((a,b,role))
    polygons = [*faces,*(tuple(i+n for i in reversed(f)) for f in faces)]
    owners = [*roles,*roles]
    for rows in edges.values():
        if len(rows) == 1:
            a,b,role = rows[0]
            polygons.append((a,a+n,b+n,b))
            owners.append(role)
    return [*points,*((x,y+.10,z) for x,y,z in points)],polygons,owners


class ShoulderAlignmentTests(unittest.TestCase):
    def test_closed_authored_rings_locate_only_two_shoulder_origins(self):
        points,faces,roles = closed_surface()
        centers, evidence = observed_shoulder_centers(points,faces,roles)
        self.assertEqual(set(centers),{"upper_arm.L","upper_arm.R"})
        self.assertAlmostEqual(centers["upper_arm.L"][0],.125)
        self.assertAlmostEqual(centers["upper_arm.R"][0],-.125)
        self.assertTrue(all(e["ring_vertex_count"] >= 4 for e in evidence.values()))
        bones = fit_canonical_biped(bounds_from_vertices(points))
        shifts,report = plan_shoulder_alignment(points,faces,roles,bones)
        self.assertEqual(set(shifts),set(centers))
        self.assertTrue(report["native_names_parents_and_axes_preserved"])

    def test_face_order_uv_split_and_scale_translation_invariance(self):
        points,faces,roles = closed_surface()
        expected,_ = observed_shoulder_centers(points,faces,roles)
        order = list(range(len(faces)))
        random.Random(91).shuffle(order)
        actual,_ = observed_shoulder_centers(points,[faces[i] for i in order],[roles[i] for i in order])
        self.assertEqual(actual,expected)
        split = [points[i] for f in faces for i in f]
        split_faces = [tuple(range(i*4,i*4+4)) for i in range(len(faces))]
        actual,_ = observed_shoulder_centers(split,split_faces,roles)
        self.assertEqual(actual,expected)
        for scale in (.01,400.):
            moved = [tuple(o+scale*v for o,v in zip((4,-2,7),p)) for p in points]
            actual,_ = observed_shoulder_centers(moved,faces,roles)
            for name,p in expected.items():
                for v,o,base in zip(actual[name],(4,-2,7),p):
                    self.assertAlmostEqual((v-o)/scale,base,places=9)

    def test_open_nonmanifold_and_missing_ownership_fail_closed(self):
        points,faces,roles = closed_surface()
        for bad_faces,bad_roles in ((faces[:-1],roles[:-1]),(faces+[faces[0]],roles+[roles[0]]),
                                    (faces,["body-core"]*len(roles))):
            with self.assertRaises(ValueError):
                observed_shoulder_centers(points,bad_faces,bad_roles)
        points,faces,roles,*_ = authored_surface()
        with self.assertRaisesRegex(ValueError,"closed manifold"):
            observed_shoulder_centers(points,faces,roles)

    def test_disjoint_cut_rings_and_already_aligned_source_are_rejected(self):
        points,faces,roles = closed_surface()
        bad = list(roles)
        index = next(i for i,(face,role) in enumerate(zip(faces,roles))
                     if role == "left-arm" and min(points[v][0] for v in face) > .3)
        bad[index] = "body-core"
        with self.assertRaisesRegex(ValueError,"Disconnected"):
            observed_shoulder_centers(points,faces,bad)
        centers,_ = observed_shoulder_centers(points,faces,roles)
        bones = fit_canonical_biped(bounds_from_vertices(points))
        aligned = [replace(b,head=centers[b.name]) if b.name in centers else b for b in bones]
        with self.assertRaisesRegex(ValueError,"already aligned"):
            plan_shoulder_alignment(points,faces,roles,aligned)


if __name__ == "__main__":
    unittest.main()
