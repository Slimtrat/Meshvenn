from __future__ import annotations

import unittest

from core.modular_character import partition_faces


class ModularPartitionTests(unittest.TestCase):
    def test_source_faces_are_selected_exactly_once_without_mutating_topology(self):
        polygons = [(0, 1, 2), (0, 2, 3), (2, 4, 3), (4, 5, 3)]
        original = polygons.copy()
        result = partition_faces(polygons, ["core", "core", "arm", "arm"],
                                 ["core", "arm"], vertex_count=6)
        self.assertEqual(polygons, original)
        self.assertEqual(result.region_faces, {"core": (0, 1), "arm": (2, 3)})
        self.assertEqual(result.region_vertices, {"core": (0, 1, 2, 3), "arm": (2, 3, 4, 5)})
        self.assertEqual(result.shared_vertices, {2: ("arm", "core"), 3: ("arm", "core")})
        self.assertIn((2, 3), result.boundary_edges["core"])
        self.assertIn((2, 3), result.boundary_edges["arm"])
        self.assertNotIn((0, 2), result.boundary_edges["core"])
        self.assertEqual(sorted(index for selection in result.region_faces.values() for index in selection),
                         list(range(len(polygons))))
        with self.assertRaises(TypeError):
            result.region_faces["core"] = ()

    def test_polygon_winding_and_ngons_are_preserved(self):
        polygons = [(0, 1, 2, 3), (3, 2, 4)]
        result = partition_faces(polygons, ("core", "arm"), ("core", "arm"), vertex_count=5)
        self.assertEqual(tuple(polygons[index] for index in result.region_faces["core"]), ((0, 1, 2, 3),))
        self.assertEqual(tuple(polygons[index] for index in result.region_faces["arm"]), ((3, 2, 4),))

    def test_no_regions_are_guessed_from_weights_or_coordinate_bands(self):
        with self.assertRaises(ValueError):
            partition_faces([(0, 1, 2)], [], ["core"], vertex_count=3)
        with self.assertRaises(ValueError):
            partition_faces([(0, 1, 2)], ["guessed"], ["core"], vertex_count=3)

    def test_incomplete_ambiguous_or_empty_ownership_fails(self):
        for ownership, regions in (([], ["core"]), (["core", "core"], ["core"]),
                                   (["core"], ["core", "unused"]), (["core"], []),
                                   (["core"], ["core", "core"]),
                                   ([["core", "arm"]], ["core", "arm"])):
            with self.assertRaises((TypeError, ValueError)):
                partition_faces([(0, 1, 2)], ownership, regions, vertex_count=3)

    def test_invalid_polygons_and_vertex_references_fail(self):
        for polygons, count in (([], 3), ([(0, 1)], 3), ([(0, 1, 1)], 3), ([(0, 1, 3)], 3),
                                ([(0, 1, -1)], 3), ([(0, 1, True)], 3), ([(0, 1, 2)], 0),
                                ([(0, 1, 2)], True)):
            with self.assertRaises((TypeError, ValueError)):
                partition_faces(polygons, ["core"], ["core"], vertex_count=count)

    def test_partition_is_deterministic_and_not_aliased(self):
        polygons = [[0, 1, 2], [0, 2, 3]]
        ownership = ["core", "arm"]
        first = partition_faces(polygons, ownership, ["core", "arm"], vertex_count=4)
        self.assertEqual(first, partition_faces(polygons, ownership, ["core", "arm"], vertex_count=4))
        ownership[0] = "arm"
        polygons[0][0] = 3
        self.assertEqual(first.region_faces["core"], (0,))
        self.assertEqual(first.region_vertices["core"], (0, 1, 2))
