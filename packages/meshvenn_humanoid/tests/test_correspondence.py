from pathlib import Path
import sys, unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from meshvenn_humanoid.correspondence import match_surface


class CorrespondenceTests(unittest.TestCase):
    def test_split_seam_and_reordered_faces_preserve_measured_surface(self):
        source = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        candidate = [source[1], source[2], source[0], source[0]]
        result = match_surface(
            source,
            candidate,
            [(0, 1, 2), (0, 2, 1)],
            [(2, 1, 0), (3, 0, 1)],
            [{"a": 1.0}] * 4,
        )
        self.assertEqual(result, [2, 0, 1])

    def test_changed_winding_missing_faces_and_displaced_surface_are_rejected(self):
        points = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        weights = [{"a": 1.0}] * 3
        for candidate, faces in (
            (points, [(0, 2, 1)]),
            (points, []),
            ([(0, 0, 0.1), *points[1:]], [(0, 1, 2)]),
        ):
            with self.assertRaises(ValueError):
                match_surface(points, candidate, [(0, 1, 2)], faces, weights)

    def test_different_weights_on_coincident_candidate_seams_are_ambiguous(self):
        source = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        candidate = [*source, source[0]]
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            match_surface(
                source,
                candidate,
                [(0, 1, 2)],
                [(0, 1, 2)],
                [{"a": 1.0}] * 3 + [{"b": 1.0}],
            )
