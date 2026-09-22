from __future__ import annotations

import math
import unittest

from core.image_mask import BinaryMask
from core.projection_alignment import ProjectionAlignment


def _mask(rows: tuple[str, ...]) -> BinaryMask:
    width = len(rows[0])
    # Rows are written bottom to top, matching Blender image coordinates.
    return BinaryMask(width, len(rows), bytes(int(pixel) for row in rows for pixel in row))


class ProjectionAlignmentTests(unittest.TestCase):
    def test_identity_preserves_exact_mask_and_source_coordinates(self) -> None:
        source = _mask(("010", "101", "010"))
        alignment = ProjectionAlignment()
        self.assertIs(alignment.align_mask(source), source)
        self.assertEqual(alignment.source_uv(0.25, 0.75), (0.25, 0.75))
        self.assertTrue(alignment.is_identity)

    def test_horizontal_and_vertical_offsets_move_silhouette(self) -> None:
        source = _mask(("00000", "00000", "00100", "00000", "00000"))
        alignment = ProjectionAlignment(offset_u=0.25, offset_v=-0.25)
        result = alignment.align_mask(source)
        self.assertEqual(result.occupied_count, 1)
        self.assertTrue(result.get(3, 1))
        self.assertFalse(result.get(2, 2))
        self.assertEqual(alignment.source_uv(0.75, 0.25), (0.5, 0.5))

    def test_uniform_scale_expands_around_center(self) -> None:
        source = _mask(("00000", "00000", "01110", "00000", "00000"))
        result = ProjectionAlignment(scale=2).align_mask(source)
        self.assertTrue(result.get(0, 2))
        self.assertTrue(result.get(2, 2))
        self.assertTrue(result.get(4, 2))
        self.assertEqual(result.occupied_count, 10)

    def test_clipped_source_coordinates_never_repeat_edge_pixels(self) -> None:
        source = _mask(("001", "000", "000"))
        shifted = ProjectionAlignment(offset_u=0.5).align_mask(source)
        self.assertFalse(any(shifted.values))
        self.assertEqual(ProjectionAlignment(offset_u=0.5).source_uv(0, 0)[0], -0.5)

    def test_single_pixel_axis_is_supported(self) -> None:
        source = _mask(("1", "0", "1"))
        result = ProjectionAlignment(offset_v=0.5).align_mask(source)
        self.assertEqual((result.width, result.height), (1, 3))
        self.assertEqual(len(result.values), 3)

    def test_parameters_are_bounded_and_json_ready(self) -> None:
        for parameters in (
            {"offset_u": math.nan},
            {"offset_v": math.inf},
            {"scale": 0},
            {"scale": 4.1},
            {"offset_u": 0.51},
        ):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                ProjectionAlignment(**parameters)
        self.assertEqual(
            ProjectionAlignment(offset_u=0.1, offset_v=-0.2, scale=1.5).as_dict(),
            {"offset_u": 0.1, "offset_v": -0.2, "scale": 1.5},
        )


if __name__ == "__main__":
    unittest.main()
