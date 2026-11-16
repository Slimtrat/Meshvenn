"""Fixed before/after controls: two set differences cannot cancel each other."""
from pathlib import Path
import tempfile
import unittest

from scripts.appearance_diagnostic_corpus.authoring import png_rgba
from scripts.diagnostic_qualification.differences import directional_differences, unavailable
from scripts.diagnostic_qualification.measure import compare_images, write_comparison
from scripts.diagnostic_qualification.presentation import difference_summary
from scripts.diagnostic_qualification.report import assemble_report


class DirectionalDifferenceTests(unittest.TestCase):
    def setUp(self):
        self.empty = (0., 0., 0., 0.)
        self.blue = (0., 0., 1., 1.)
        self.red = (1., 0., 0., 1.)

    def differences(self, old, new, mask):
        return directional_differences(tuple(c for p in old for c in p), tuple(c for p in new for c in p),
                                       bytes(mask), len(old), 1)

    def test_identical_before_after_have_two_empty_differences(self):
        result = self.differences([self.red, self.blue], [self.red, self.blue], [1, 0])
        self.assertTrue(result["before_minus_after"]["outside_edit_mask_empty"])
        self.assertTrue(result["after_minus_before"]["outside_edit_mask_empty"])
        self.assertTrue(result["outside_edit_mask"]["rgba_difference_empty"])

    def test_removal_and_addition_of_equal_area_never_cancel(self):
        old, new = [self.red, self.blue, self.empty], [self.blue, self.empty, self.red]
        result = self.differences(old, new, [1, 0, 0])
        self.assertEqual(result["before_minus_after"]["outside_edit_mask_pixels"], 1)
        self.assertEqual(result["after_minus_before"]["outside_edit_mask_pixels"], 1)
        self.assertEqual(result["outside_edit_mask"]["foreground_symmetric_difference_pixels"], 2)
        self.assertEqual(result["outside_edit_mask"]["status"], "fail")
        inverse = self.differences(new, old, [1, 0, 0])
        self.assertEqual(inverse["before_minus_after"], result["after_minus_before"])
        self.assertEqual(inverse["after_minus_before"], result["before_minus_after"])

    def test_unchanged_silhouette_does_not_hide_recolouring_or_alpha_drift(self):
        for changed in (self.red, (0., 0., 1., .75)):
            result = self.differences([self.red, self.blue], [self.blue, changed], [1, 0])
            self.assertTrue(result["outside_edit_mask"]["foreground_difference_empty"])
            self.assertFalse(result["outside_edit_mask"]["rgba_difference_empty"])
            self.assertEqual(result["outside_edit_mask"]["rgba_before_minus_after_samples"], 1)
            self.assertEqual(result["outside_edit_mask"]["rgba_after_minus_before_samples"], 1)
            self.assertEqual(result["outside_edit_mask"]["status"], "fail")

    def test_authorized_badge_change_is_not_required_to_be_globally_empty(self):
        result = self.differences([self.red, self.blue], [self.blue, self.blue], [1, 0])
        self.assertTrue(result["outside_edit_mask"]["rgba_difference_empty"])
        self.assertFalse(result["full_image"]["rgba_difference_empty"])
        self.assertEqual(result["full_image"]["changed_rgba_pixels"], 1)

    def test_unavailable_or_incomplete_grid_never_means_empty(self):
        result = unavailable("image_grid_changed")
        self.assertIsNone(result["before_minus_after"]["outside_edit_mask_empty"])
        self.assertIsNone(result["after_minus_before"]["outside_edit_mask_empty"])
        self.assertIsNone(result["outside_edit_mask"]["rgba_difference_empty"])
        html = difference_summary({"directional_differences": result})
        self.assertIn("Non calculable", html)
        self.assertIn("dimensions des images diffèrent", html)
        with self.assertRaises(ValueError):
            directional_differences(self.blue, self.blue * 2, b"\1", 1, 1)

    def test_pixel_files_and_direction_maps_are_actual_original_bound_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            values = {"healthy": (self.blue, self.blue, self.empty), "before": (self.red, self.blue, self.empty),
                      "after": (self.blue, self.empty, self.red), "mask": ((1., 1., 1., 1.), (0., 0., 0., 1.), (0., 0., 0., 1.))}
            paths = {}
            for name, pixels in values.items():
                paths[name] = folder / (name + ".png")
                paths[name].write_bytes(png_rgba(3, 1, bytes(int(c * 255) for p in pixels for c in p)))
            original = {name: p.read_bytes() for name, p in paths.items()}
            result = write_comparison(*(paths[k] for k in ("healthy", "before", "after", "mask")), folder / "delta.png")
            self.assertEqual(result["outside_mask_changed_pixels"], 2)
            delta = result["directional_differences"]
            self.assertEqual(len(delta["artifacts"]), 2)
            from core.diagnostics_preflight import RasterInput
            for artifact in delta["artifacts"]:
                raster = RasterInput.from_path(folder / artifact["path"])
                self.assertEqual(raster.source_sha256, artifact["sha256"])
                coloured = [raster.rgba[i:i+3] for i in range(0, len(raster.rgba), 4)]
                expected = (210/255,45/255,65/255) if artifact["kind"] == "before_minus_after" else (45/255,95/255,210/255)
                self.assertEqual(coloured.count(expected), 1)
            self.assertEqual(original, {name: p.read_bytes() for name, p in paths.items()})
            # A healthy reference cannot replace the actual before image in A\\B.
            noop = compare_images(paths["healthy"], paths["before"], paths["before"], paths["mask"])
            self.assertEqual(noop["directional_differences"]["full_image"]["changed_rgba_pixels"], 0)

    def test_directional_failure_cannot_be_hidden_by_an_inconsistent_old_summary(self):
        report = assemble_report({"status": "pass", "all_full_matrices_passed": True},
            comparison={"outside_pixels_status": "pass", "directional_differences":
                        {"before_minus_after": {"outside_edit_mask_empty": False},
                         "after_minus_before": {"outside_edit_mask_empty": True}}})
        self.assertEqual(report["qualification_status"], "fail")


if __name__ == "__main__":
    unittest.main()
