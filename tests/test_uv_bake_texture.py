from tests.uv_bake_test_support import *

class TextureBufferTests(
    unittest.TestCase
):
    def test_filled_texture(
        self,
    ) -> None:
        texture = (
            TextureBuffer.filled(
                2,
                3,
                (
                    0.25,
                    0.5,
                    0.75,
                    1.0,
                ),
            )
        )

        self.assertEqual(
            texture.pixel_count,
            6,
        )

        for y in range(
            3
        ):
            for x in range(
                2
            ):
                color = (
                    texture.rgba(
                        x,
                        y,
                    )
                )

                self.assertAlmostEqual(
                    color[0],
                    0.25,
                )

                self.assertAlmostEqual(
                    color[1],
                    0.5,
                )

                self.assertAlmostEqual(
                    color[2],
                    0.75,
                )

                self.assertAlmostEqual(
                    color[3],
                    1.0,
                )

    def test_set_rgba(
        self,
    ) -> None:
        texture = (
            TextureBuffer.filled(
                2,
                2,
                (
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ),
            )
        )

        texture.set_rgba(
            1,
            0,
            (
                1.0,
                0.5,
                0.25,
                1.0,
            ),
        )

        result = (
            texture.rgba(
                1,
                0,
            )
        )

        self.assertAlmostEqual(
            result[0],
            1.0,
        )

        self.assertAlmostEqual(
            result[1],
            0.5,
        )

        self.assertAlmostEqual(
            result[2],
            0.25,
        )

        self.assertAlmostEqual(
            result[3],
            1.0,
        )

    def test_copy_pixel(
        self,
    ) -> None:
        texture = (
            TextureBuffer.filled(
                2,
                1,
                (
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ),
            )
        )

        texture.set_rgba(
            0,
            0,
            (
                1.0,
                0.25,
                0.5,
                1.0,
            ),
        )

        texture.copy_pixel(
            0,
            1,
        )

        self.assertEqual(
            texture.rgba(
                0,
                0,
            ),
            texture.rgba(
                1,
                0,
            ),
        )

    def test_invalid_buffer_length(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            TextureBuffer(
                width=2,
                height=2,
                pixels=array(
                    "f",
                    [
                        0.0,
                        0.0,
                    ],
                ),
            )

    def test_outside_coordinate_is_rejected(
        self,
    ) -> None:
        texture = (
            TextureBuffer.filled(
                2,
                2,
                (
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                ),
            )
        )

        with self.assertRaises(
            IndexError
        ):
            texture.rgba(
                2,
                0,
            )


# =========================================================
# Basic rasterization
# =========================================================
