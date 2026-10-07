import math
import unittest

from scripts.head_isolation_metrics import masked_edge_summary, rigid_residual


class HeadMetricsTests(unittest.TestCase):
    def setUp(self):
        self.rest = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        self.faces = [(0, 1, 2)]

    def test_rigid_transform_is_not_surface_strain(self):
        moved = [(3-y, 4+x, 5+z) for x,y,z in self.rest]
        edges = masked_edge_summary(self.rest, moved, self.faces, [True]*3, 1)
        self.assertEqual(edges["edge_count"], 3)
        self.assertEqual(edges["max_abs_log_length_ratio"], 0)
        self.assertEqual(rigid_residual(self.rest, moved, moved, [True]*3, 1)["max_residual_in_heights"], 0)

    def test_compression_and_extension_are_symmetric(self):
        for scale in (.5, 2):
            posed = [(scale*x, scale*y, z) for x,y,z in self.rest]
            edges = masked_edge_summary(self.rest, posed, self.faces, [True]*3, 1)
            self.assertAlmostEqual(edges["p95_abs_log_length_ratio"], math.log(2))

    def test_collapsed_edges_remain_failures_and_seams_do_not_inflate_count(self):
        posed = [(0, 0, 0)]*3
        edges = masked_edge_summary(self.rest*2, posed*2, self.faces+[(3, 4, 5)], [True]*6, 1)
        self.assertEqual(edges["collapsed_fraction"], 1)
        self.assertEqual(edges["edge_count"], 3)
        # Worst seam variant wins, not an average that hides the collapsed copy.
        edges = masked_edge_summary(self.rest*2, self.rest+posed, self.faces+[(3, 4, 5)], [True]*6, 1)
        self.assertEqual(edges["collapsed_fraction"], 1)

    def test_empty_nonfinite_wrong_topology_and_nonboolean_cohort_are_rejected(self):
        for mask in ([False]*3, [1]*3, [True]):
            with self.assertRaises(ValueError):
                masked_edge_summary(self.rest, self.rest, self.faces, mask, 1)
        with self.assertRaises(ValueError):
            rigid_residual(self.rest, self.rest, [(math.nan, 0, 0)]*3, [True]*3, 1)
        with self.assertRaises(ValueError):
            masked_edge_summary(self.rest, self.rest, [(0, 1, 5)], [True]*3, 1)

    def test_residual_is_height_normalized(self):
        posed = [(x+.1, y, z) for x,y,z in self.rest]
        residual = rigid_residual(self.rest, posed, self.rest, [True]*3, 2)
        self.assertAlmostEqual(residual["max_residual_in_heights"], .05)


if __name__ == "__main__":
    unittest.main()
