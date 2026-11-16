"""Fixed authored pixels expose deleted parts, wrong grids and unrelated edits."""
from pathlib import Path
import tempfile
import unittest

from scripts.appearance_diagnostic_corpus.authoring import png_rgba
from scripts.diagnostic_qualification.measure import compare_images, write_comparison


class PixelEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.good = self.image("healthy", [(30, 130, 90, 255), (240, 200, 25, 255)])
        self.bad = self.image("before", [(200, 20, 160, 255), (240, 200, 25, 255)])
        self.mask = self.image("mask", [(255, 255, 255, 255), (0, 0, 0, 0)])

    def image(self, name, pixels):
        path = self.root / (name + ".png")
        path.write_bytes(png_rgba(len(pixels), 1, bytes(c for p in pixels for c in p)))
        return path

    def test_true_local_repair_still_does_not_certify_identity(self):
        hashes = {p: p.read_bytes() for p in (self.good, self.bad, self.mask)}
        result = write_comparison(self.good, self.bad, self.good, self.mask, self.root / "overlay.png")
        self.assertGreater(result["numerical_improvement"], 0)
        self.assertEqual(result["outside_pixels_status"], "pass")
        self.assertEqual(result["semantic_identity_status"], "unknown")
        self.assertEqual(result["qualification_status"], "unknown")
        self.assertTrue((self.root / result["overlay"]["path"]).is_file())
        self.assertEqual(hashes, {p: p.read_bytes() for p in hashes})

    def test_colour_improvement_cannot_hide_a_deleted_protected_part(self):
        erased = self.image("erased", [(30, 130, 90, 255), (0, 0, 0, 0)])
        result = compare_images(self.good, self.bad, erased, self.mask)
        self.assertGreater(result["numerical_improvement"], 0)
        self.assertEqual(result["outside_pixels_status"], "fail")
        self.assertEqual(result["outside_mask_changed_pixels"], 1)
        self.assertEqual(result["foreground_alpha_iou"], .5)

    def test_regridding_is_reported_without_silent_resize(self):
        resized = self.image("resized", [(30, 130, 90, 255)] * 4)
        result = compare_images(self.good, self.bad, resized, self.mask)
        self.assertEqual(result["reason"], "image_grid_changed")
        self.assertNotIn("numerical_improvement", result)

    def test_empty_mask_and_noop_are_not_successful_corrections(self):
        empty = self.image("empty", [(0, 0, 0, 0)] * 2)
        with self.assertRaises(ValueError):
            compare_images(self.good, self.bad, self.good, empty)
        result = compare_images(self.good, self.bad, self.bad, self.mask)
        self.assertEqual(result["numerical_improvement"], 0)


if __name__ == "__main__":
    unittest.main()
