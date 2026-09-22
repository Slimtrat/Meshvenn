from tests.uv_bake_test_support import *

class UVBakePaddingTests(
    unittest.TestCase
):
    def test_one_pixel_island_gets_four_neighbours_with_padding_one(
        self,
    ) -> None:
        triangle = UVBakeTriangle(
            a=vertex(
                0.0,
                0.0,
                0.0,
                0.26,
                0.26,
            ),
            b=vertex(
                1.0,
                0.0,
                0.0,
                0.49,
                0.26,
            ),
            c=vertex(
                0.0,
                1.0,
                0.0,
                0.26,
                0.49,
            ),
        )

        result = (
            bake_uv_texture(
                [
                    triangle
                ],
                constant_sampler(
                    (
                        1.0,
                        0.25,
                        0.0,
                        1.0,
                    )
                ),
                config=UVBakeConfig(
                    width=4,
                    height=4,
                    padding_pixels=1,
                ),
            )
        )

        self.assertEqual(
            result.stats.covered_pixels,
            1,
        )

        self.assertEqual(
            result.stats.padded_pixels,
            4,
        )

        self.assertEqual(
            result.stats.filled_pixels,
            5,
        )

        self.assertTrue(
            result.is_covered(
                1,
                1,
            )
        )

        self.assertTrue(
            result.is_filled(
                0,
                1,
            )
        )

        self.assertTrue(
            result.is_filled(
                2,
                1,
            )
        )

        self.assertTrue(
            result.is_filled(
                1,
                0,
            )
        )

        self.assertTrue(
            result.is_filled(
                1,
                2,
            )
        )

        self.assertFalse(
            result.is_covered(
                0,
                1,
            )
        )

    def test_padding_copies_source_color(
        self,
    ) -> None:
        color = (
            0.8,
            0.4,
            0.2,
            1.0,
        )

        triangle = UVBakeTriangle(
            a=vertex(
                0.0,
                0.0,
                0.0,
                0.26,
                0.26,
            ),
            b=vertex(
                1.0,
                0.0,
                0.0,
                0.49,
                0.26,
            ),
            c=vertex(
                0.0,
                1.0,
                0.0,
                0.26,
                0.49,
            ),
        )

        result = (
            bake_uv_texture(
                [
                    triangle
                ],
                constant_sampler(
                    color
                ),
                config=UVBakeConfig(
                    width=4,
                    height=4,
                    padding_pixels=1,
                ),
            )
        )

        original = (
            result.texture.rgba(
                1,
                1,
            )
        )

        padded = (
            result.texture.rgba(
                2,
                1,
            )
        )

        for (
            a,
            b,
        ) in zip(
            original,
            padded,
            strict=True,
        ):
            self.assertAlmostEqual(
                a,
                b,
                places=6,
            )

    def test_padding_zero_does_not_expand_texture(
        self,
    ) -> None:
        result = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                constant_sampler(),
                config=UVBakeConfig(
                    width=4,
                    height=4,
                    padding_pixels=0,
                ),
            )
        )

        self.assertEqual(
            result.stats.padded_pixels,
            0,
        )

        self.assertEqual(
            result.coverage,
            result.filled,
        )


# =========================================================
# Progress
# =========================================================
