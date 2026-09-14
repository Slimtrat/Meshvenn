from __future__ import annotations

from tests.sdf_test_support import *


class SignedDistanceMaskTests(
    unittest.TestCase
):
    def test_single_pixel_exact_axis_distances(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_single_pixel_mask(),
                horizontal_extent=1.0,
                vertical_extent=1.0,
            )
        )

        # 5 samples span [-1, +1]:
        #
        #     spacing = 2 / 4 = 0.5

        self.assertAlmostEqual(
            field.horizontal_spacing,
            0.5,
        )

        self.assertAlmostEqual(
            field.vertical_spacing,
            0.5,
        )

        self.assertAlmostEqual(
            field.get(
                2,
                2,
            ),
            -0.5,
            places=6,
        )

        self.assertAlmostEqual(
            field.get(
                3,
                2,
            ),
            0.5,
            places=6,
        )

        self.assertAlmostEqual(
            field.get(
                4,
                2,
            ),
            1.0,
            places=6,
        )

    def test_single_pixel_exact_diagonal_distance(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_single_pixel_mask(),
                horizontal_extent=1.0,
                vertical_extent=1.0,
            )
        )

        self.assertAlmostEqual(
            field.get(
                4,
                4,
            ),
            math.sqrt(
                2.0
            ),
            places=6,
        )

    def test_square_center_is_deeper_than_boundary(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_square_mask()
            )
        )

        center = (
            field.get(
                3,
                3,
            )
        )

        boundary = (
            field.get(
                2,
                3,
            )
        )

        outside = (
            field.get(
                1,
                3,
            )
        )

        self.assertLess(
            center,
            boundary,
        )

        self.assertLess(
            boundary,
            0.0,
        )

        self.assertGreater(
            outside,
            0.0,
        )

    def test_circle_has_correct_sign(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                circle_mask_9()
            )
        )

        self.assertLess(
            field.get(
                4,
                4,
            ),
            0.0,
        )

        self.assertLess(
            field.get(
                4,
                1,
            ),
            0.0,
        )

        self.assertGreater(
            field.get(
                0,
                0,
            ),
            0.0,
        )

    def test_empty_mask_remains_finite_and_outside(
        self,
    ) -> None:
        mask = BinaryMask(
            width=5,
            height=5,
            values=bytes(
                25
            ),
        )

        field = (
            build_signed_distance_mask(
                mask
            )
        )

        self.assertTrue(
            field.empty
        )

        self.assertFalse(
            field.full
        )

        for value in (
            field.values
        ):
            self.assertTrue(
                math.isfinite(
                    value
                )
            )

            self.assertGreater(
                value,
                0.0,
            )

    def test_full_mask_remains_finite_and_inside(
        self,
    ) -> None:
        mask = BinaryMask(
            width=5,
            height=5,
            values=bytes(
                [
                    1
                ]
                * 25
            ),
        )

        field = (
            build_signed_distance_mask(
                mask
            )
        )

        self.assertTrue(
            field.full
        )

        self.assertFalse(
            field.empty
        )

        for value in (
            field.values
        ):
            self.assertTrue(
                math.isfinite(
                    value
                )
            )

            self.assertLess(
                value,
                0.0,
            )

    def test_bilinear_sampling_preserves_center_sign(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_square_mask()
            )
        )

        value = (
            field.sample_uv(
                0.5,
                0.5,
            )
        )

        self.assertLess(
            value,
            0.0,
        )

    def test_sampling_outside_image_is_positive(
        self,
    ) -> None:
        field = (
            build_signed_distance_mask(
                centered_square_mask()
            )
        )

        self.assertGreater(
            field.sample_uv(
                -0.25,
                0.5,
            ),
            0.0,
        )

        self.assertGreater(
            field.sample_uv(
                1.25,
                0.5,
            ),
            0.0,
        )

    def test_invalid_extents_are_rejected(
        self,
    ) -> None:
        mask = (
            centered_square_mask()
        )

        for value in (
            0.0,
            -1.0,
            math.inf,
            math.nan,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    build_signed_distance_mask(
                        mask,
                        horizontal_extent=value,
                    )

    def test_wrong_mask_type_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            build_signed_distance_mask(
                object()
            )
