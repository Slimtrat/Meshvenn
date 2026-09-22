from __future__ import annotations

from tests.sdf_test_support import *


class SDFVolumeTests(
    unittest.TestCase
):
    def test_index_layout_x_is_fastest(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    0.0,
                    1.0,
                    2.0,
                    3.0,
                    4.0,
                    5.0,
                    6.0,
                    7.0,
                ),
            ),
        )

        self.assertEqual(
            volume.index(
                0,
                0,
                0,
            ),
            0,
        )

        self.assertEqual(
            volume.index(
                1,
                0,
                0,
            ),
            1,
        )

        self.assertEqual(
            volume.index(
                0,
                1,
                0,
            ),
            2,
        )

        self.assertEqual(
            volume.index(
                0,
                0,
                1,
            ),
            4,
        )

    def test_trilinear_center_is_average_of_corners(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    0.0,
                    1.0,
                    2.0,
                    3.0,
                    4.0,
                    5.0,
                    6.0,
                    7.0,
                ),
            ),
        )

        self.assertAlmostEqual(
            volume.sample_normalized(
                0.0,
                0.0,
                0.0,
            ),
            3.5,
            places=6,
        )

    def test_inside_uses_iso_level(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                ),
            ),
        )

        self.assertTrue(
            volume.inside(
                0,
                0,
                0,
            )
        )

        self.assertFalse(
            volume.inside(
                1,
                0,
                0,
            )
        )

    def test_cell_surface_crossing(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                    1.0,
                ),
            ),
        )

        self.assertTrue(
            volume.cell_crosses_surface(
                0,
                0,
                0,
            )
        )

    def test_constant_inside_cell_does_not_cross_surface(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                    -1.0,
                ),
            ),
        )

        self.assertFalse(
            volume.cell_crosses_surface(
                0,
                0,
                0,
            )
        )

    def test_occupancy_conversion(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    1.0,
                    0.0,
                    2.0,
                    -2.0,
                    3.0,
                    -3.0,
                    4.0,
                ),
            ),
        )

        self.assertEqual(
            volume.to_occupancy_bytes(),
            bytes(
                (
                    1,
                    0,
                    1,
                    0,
                    1,
                    0,
                    1,
                    0,
                )
            ),
        )

    def test_wrong_value_count_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            SDFVolume(
                width=2,
                depth=2,
                height=2,
                values=array(
                    "f",
                    (
                        0.0,
                    ),
                ),
            )
