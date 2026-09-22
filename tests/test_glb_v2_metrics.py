"""V2 benchmark semantics, including unusable images and absent reconstructions."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from core.image_mask import BinaryMask
from scripts.glb_v2_metrics import mask_iou, score_silhouettes


@dataclass(frozen=True)
class View:
    name: str
    mask: BinaryMask
    valid: bool = True


class GLBV2MetricTests(unittest.TestCase):
    def test_perfect_and_partial_matches(self) -> None:
        reference = BinaryMask(2, 2, bytes((1, 1, 0, 0)))
        self.assertEqual(mask_iou(reference, reference), 1.0)
        self.assertEqual(mask_iou(reference, BinaryMask(2, 2, bytes((1, 0, 1, 0)))), 1 / 3)

    def test_empty_images_cannot_earn_success(self) -> None:
        blank = BinaryMask(2, 2, bytes(4))
        self.assertEqual(mask_iou(blank, blank), 0.0)
        report = score_silhouettes([View("000", blank, False)], [View("000", blank, False)])
        self.assertEqual(report["mean_iou"], 0.0)
        self.assertEqual(report["valid_input_views"], 0)

    def test_missing_output_view_scores_zero(self) -> None:
        visible = BinaryMask(2, 2, bytes((1, 1, 0, 0)))
        blank = BinaryMask(2, 2, bytes(4))
        report = score_silhouettes(
            [View("000", visible), View("045", visible)],
            [View("000", visible), View("045", blank, False)],
        )
        self.assertEqual(report["mean_iou"], 0.5)
        self.assertEqual(report["valid_input_views"], 2)

    def test_mismatched_dimensions_or_views_fail(self) -> None:
        with self.assertRaises(ValueError):
            mask_iou(BinaryMask(1, 1, b"\x01"), BinaryMask(2, 1, b"\x01\x01"))
        with self.assertRaises(ValueError):
            score_silhouettes([View("000", BinaryMask(1, 1, b"\x01"))], [])


if __name__ == "__main__":
    unittest.main()
