"""Blender self-check for the V2 3D metric before scoring reconstructions."""

from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path

from mathutils import Vector

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.glb_v2_surface_metrics import compare_glb_surfaces, compare_surface_bvh


def _triangles(rows):
    return [tuple(Vector(point) for point in triangle) for triangle in rows]


class SurfaceDetailTests(unittest.TestCase):
    def setUp(self):
        self.plane = _triangles([((0, 0, 0), (1, 0, 0), (1, 1, 0)),
                                 ((0, 0, 0), (1, 1, 0), (0, 1, 0))])

    def test_identical_surface_is_finite_and_deterministic(self):
        first = compare_surface_bvh(self.plane, self.plane, samples=256)
        self.assertEqual(first, compare_surface_bvh(self.plane, self.plane, samples=256))
        self.assertLess(first["symmetric_distance"]["max"], 1e-6)
        self.assertTrue(all(row["fscore"] == 1.0 for row in first["fscore_by_threshold"]))
        normals = first["reference_to_candidate_normals"]
        self.assertAlmostEqual(normals["signed_dot_mean"], 1.0, places=6)
        self.assertEqual(normals["opposed_fraction"], 0.0)
        json.dumps(first, allow_nan=False)

    def test_exact_surface_distance_does_not_depend_on_triangulation(self):
        fan = _triangles([((0, 0, 0), (1, 0, 0), (.5, .5, 0)),
                          ((1, 0, 0), (1, 1, 0), (.5, .5, 0)),
                          ((1, 1, 0), (0, 1, 0), (.5, .5, 0)),
                          ((0, 1, 0), (0, 0, 0), (.5, .5, 0))])
        report = compare_surface_bvh(self.plane, fan, samples=128)
        self.assertLess(report["symmetric_distance"]["max"], 1e-6)
        self.assertTrue(all(row["fscore"] == 1.0 for row in report["fscore_by_threshold"]))

    def test_small_displacement_is_visible_at_fine_thresholds(self):
        moved = [tuple(point + Vector((0, 0, .015)) for point in triangle)
                 for triangle in self.plane]
        report = compare_surface_bvh(self.plane, moved, samples=256)
        self.assertAlmostEqual(report["symmetric_distance"]["mean"], .015, places=6)
        self.assertAlmostEqual(report["symmetric_distance"]["p95"], .015, places=6)
        self.assertEqual([row["fscore"] for row in report["fscore_by_threshold"]], [0., 0., 1.])

    def test_flipped_faces_are_not_hidden_by_perfect_distance(self):
        flipped = [tuple(reversed(triangle)) for triangle in self.plane]
        report = compare_surface_bvh(self.plane, flipped, samples=256)
        self.assertTrue(all(row["fscore"] == 1.0 for row in report["fscore_by_threshold"]))
        normals = report["reference_to_candidate_normals"]
        self.assertAlmostEqual(normals["signed_dot_mean"], -1.0, places=6)
        self.assertEqual(normals["opposed_fraction"], 1.0)
        self.assertAlmostEqual(normals["angle_degrees_p95"], 180., places=6)

    def test_directional_scores_expose_missing_surface(self):
        half = _triangles([((0, 0, 0), (.5, 0, 0), (.5, 1, 0)),
                           ((0, 0, 0), (.5, 1, 0), (0, 1, 0))])
        report = compare_surface_bvh(self.plane, half, samples=1024)
        tight = report["fscore_by_threshold"][0]
        self.assertEqual(tight["precision"], 1.0)
        self.assertGreater(tight["recall"], .45)
        self.assertLess(tight["recall"], .60)
        self.assertLess(tight["fscore"], .75)

    def test_unrelated_normals_do_not_claim_correspondences(self):
        moved = [tuple(point + Vector((0, 0, 1)) for point in triangle)
                 for triangle in self.plane]
        report = compare_surface_bvh(self.plane, moved, samples=128)
        normals = report["reference_to_candidate_normals"]
        self.assertEqual(normals["correspondence_count"], 0)
        self.assertIsNone(normals["signed_dot_mean"])
        json.dumps(report, allow_nan=False)

    def test_topology_welds_exact_seams_and_exposes_bad_winding(self):
        report = compare_surface_bvh(self.plane, self.plane, samples=128)
        topology = report["candidate_topology"]
        self.assertEqual(topology["unique_position_count"], 4)
        self.assertEqual(topology["boundary_edge_count"], 4)
        self.assertEqual(topology["nonmanifold_edge_count"], 0)
        self.assertEqual(topology["nonmanifold_vertex_count"], 0)
        self.assertEqual(topology["inconsistent_winding_edge_count"], 0)
        mixed = [self.plane[0], tuple(reversed(self.plane[1]))]
        report = compare_surface_bvh(self.plane, mixed, samples=128)
        self.assertEqual(report["candidate_topology"]["inconsistent_winding_edge_count"], 1)

    def test_nonmanifold_edge_and_bowtie_vertex_are_reported(self):
        extra = _triangles([((0, 0, 0), (1, 1, 0), (0, 0, 1))])
        report = compare_surface_bvh(self.plane, self.plane + extra, samples=128)
        self.assertEqual(report["candidate_topology"]["nonmanifold_edge_count"], 1)
        self.assertEqual(report["candidate_topology"]["nonmanifold_vertex_count"], 2)
        bowtie = _triangles([((0, 0, 0), (0, -1, 0), (-1, 0, 0))])
        report = compare_surface_bvh(self.plane, self.plane + bowtie, samples=128)
        self.assertEqual(report["candidate_topology"]["nonmanifold_edge_count"], 0)
        self.assertEqual(report["candidate_topology"]["nonmanifold_vertex_count"], 1)

    def test_closed_manifold_has_no_false_topology_defects(self):
        a, b, c, d = (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)
        tetrahedron = _triangles([(a, c, b), (a, b, d), (a, d, c), (b, c, d)])
        report = compare_surface_bvh(tetrahedron, tetrahedron, samples=128)
        topology = report["candidate_topology"]
        for name in ("boundary_edge_count", "nonmanifold_edge_count",
                     "nonmanifold_vertex_count", "inconsistent_winding_edge_count"):
            self.assertEqual(topology[name], 0)
        self.assertFalse(topology["self_intersections_checked"])

    def test_degenerate_triangles_are_reported_but_not_sampled(self):
        degenerate = _triangles([((0, 0, 0), (0, 0, 0), (0, 0, 0))])
        report = compare_surface_bvh(self.plane, self.plane + degenerate, samples=128)
        self.assertEqual(report["candidate_topology"]["degenerate_triangle_count"], 1)
        self.assertTrue(all(row["fscore"] == 1.0 for row in report["fscore_by_threshold"]))
        with self.assertRaises(ValueError):
            compare_surface_bvh(self.plane, degenerate, samples=128)

    def test_invalid_inputs_fail_closed(self):
        for count in (True, 127, 128.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                compare_surface_bvh(self.plane, self.plane, samples=count)
        nonfinite = _triangles([((0, 0, 0), (float("nan"), 0, 0), (0, 1, 0))])
        with self.assertRaises(ValueError):
            compare_surface_bvh(self.plane, nonfinite, samples=128)


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceDetailTests)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise AssertionError("Exact triangle surface metric self-check failed")
    assets = REPO_ROOT / "example" / "v2" / "assets"
    avocado = assets / "Avocado.glb"
    same = compare_glb_surfaces(avocado, avocado, samples=512)
    different = compare_glb_surfaces(avocado, assets / "BoomBox.glb", samples=512)
    if same["surface_fscore"] != 1.0 or same["symmetric_chamfer_mean"] > 1e-7:
        raise AssertionError("Identical GLB surfaces must score as identical")
    if any(row["fscore"] != 1.0 for row in same["surface_bvh"]["fscore_by_threshold"]):
        raise AssertionError("Identical GLB surfaces must match at every fine BVH threshold")
    if different["surface_fscore"] >= 0.25:
        raise AssertionError("Unrelated GLB surfaces scored as a match")
    print(f"V2 3D metric self-check: identical={same['surface_fscore']:.3f}, "
          f"different={different['surface_fscore']:.3f}")


if __name__ == "__main__":
    main()
