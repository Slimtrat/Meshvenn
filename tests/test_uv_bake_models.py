from tests.uv_bake_test_support import *

class UVBakeVertexTests(
    unittest.TestCase
):
    def test_vertex_normal_is_normalized(
        self,
    ) -> None:
        item = UVBakeVertex(
            position=(
                1.0,
                2.0,
                3.0,
            ),
            normal=(
                0.0,
                0.0,
                5.0,
            ),
            uv=(
                0.25,
                0.75,
            ),
        )

        self.assertEqual(
            item.position,
            (
                1.0,
                2.0,
                3.0,
            ),
        )

        self.assertEqual(
            item.normal,
            (
                0.0,
                0.0,
                1.0,
            ),
        )

    def test_zero_normal_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            UVBakeVertex(
                position=(
                    0.0,
                    0.0,
                    0.0,
                ),
                normal=(
                    0.0,
                    0.0,
                    0.0,
                ),
                uv=(
                    0.0,
                    0.0,
                ),
            )

    def test_non_finite_position_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            vertex(
                math.inf,
                0.0,
                0.0,
                0.0,
                0.0,
            )

    def test_uv_may_exist_outside_unit_square(
        self,
    ) -> None:
        item = vertex(
            0.0,
            0.0,
            0.0,
            -0.25,
            1.25,
        )

        self.assertEqual(
            item.uv,
            (
                -0.25,
                1.25,
            ),
        )


# =========================================================
# UVBakeTriangle
# =========================================================

class UVBakeTriangleTests(
    unittest.TestCase
):
    def test_unit_triangle_area(
        self,
    ) -> None:
        triangle = (
            unit_triangle()
        )

        self.assertAlmostEqual(
            triangle
            .signed_uv_area_twice,
            1.0,
        )

        self.assertAlmostEqual(
            triangle
            .absolute_uv_area,
            0.5,
        )

    def test_reversed_triangle_area_is_negative(
        self,
    ) -> None:
        triangle = (
            reversed_unit_triangle()
        )

        self.assertAlmostEqual(
            triangle
            .signed_uv_area_twice,
            -1.0,
        )

        self.assertAlmostEqual(
            triangle
            .absolute_uv_area,
            0.5,
        )

    def test_triangle_detects_uv_outside_unit_square(
        self,
    ) -> None:
        triangle = UVBakeTriangle(
            a=vertex(
                0.0,
                0.0,
                0.0,
                -0.1,
                0.0,
            ),
            b=vertex(
                1.0,
                0.0,
                0.0,
                1.0,
                0.0,
            ),
            c=vertex(
                0.0,
                1.0,
                0.0,
                0.0,
                1.0,
            ),
        )

        self.assertTrue(
            triangle
            .has_uv_outside_unit_square
        )


# =========================================================
# UVBakeConfig
# =========================================================

class UVBakeConfigTests(
    unittest.TestCase
):
    def test_default_config_is_valid(
        self,
    ) -> None:
        config = (
            UVBakeConfig()
        )

        config.validate()

    def test_default_texture_size_is_512(
        self,
    ) -> None:
        """
        Product decision guard.

        The benchmark selected 512² as the smallest tested
        resolution satisfying the current UV-density target.

        This test prevents core defaults from silently
        drifting back to 1024 or another value.
        """

        self.assertEqual(
            DEFAULT_TEXTURE_SIZE,
            512,
        )

        config = (
            UVBakeConfig()
        )

        self.assertEqual(
            config.width,
            512,
        )

        self.assertEqual(
            config.height,
            512,
        )

        self.assertEqual(
            config.width,
            DEFAULT_TEXTURE_SIZE,
        )

        self.assertEqual(
            config.height,
            DEFAULT_TEXTURE_SIZE,
        )

    def test_invalid_width_is_rejected(
        self,
    ) -> None:
        for value in (
            0,
            -1,
            MAX_TEXTURE_DIMENSION
            + 1,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    UVBakeConfig(
                        width=value
                    ).validate()

    def test_invalid_height_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            UVBakeConfig(
                height=(
                    MAX_TEXTURE_DIMENSION
                    + 1
                )
            ).validate()

    def test_invalid_padding_is_rejected(
        self,
    ) -> None:
        for value in (
            -1,
            MAX_PADDING_PIXELS
            + 1,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    UVBakeConfig(
                        padding_pixels=value
                    ).validate()

    def test_invalid_samples_per_axis_is_rejected(
        self,
    ) -> None:
        for value in (
            0,
            MAX_SAMPLES_PER_AXIS
            + 1,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    UVBakeConfig(
                        samples_per_axis=value
                    ).validate()

    def test_negative_barycentric_epsilon_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            UVBakeConfig(
                barycentric_epsilon=-0.1
            ).validate()

    def test_zero_degenerate_epsilon_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            UVBakeConfig(
                degenerate_uv_epsilon=0.0
            ).validate()

    def test_non_finite_background_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            UVBakeConfig(
                background_color=(
                    0.0,
                    0.0,
                    math.nan,
                    1.0,
                )
            ).validate()


# =========================================================
# TextureBuffer
# =========================================================
