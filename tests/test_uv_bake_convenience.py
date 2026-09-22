from tests.uv_bake_test_support import *

class UVBakeConvenienceTests(
    unittest.TestCase
):
    def test_square_texture_config(
        self,
    ) -> None:
        config = (
            square_texture_config(
                2048,
                padding_pixels=16,
                samples_per_axis=2,
            )
        )

        self.assertEqual(
            config.width,
            2048,
        )

        self.assertEqual(
            config.height,
            2048,
        )

        self.assertEqual(
            config.padding_pixels,
            16,
        )

        self.assertEqual(
            config.samples_per_axis,
            2,
        )

        config.validate()

    def test_explicit_high_quality_size_is_not_affected_by_default(
        self,
    ) -> None:
        config = (
            square_texture_config(
                1024
            )
        )

        self.assertEqual(
            config.width,
            1024,
        )

        self.assertEqual(
            config.height,
            1024,
        )

    def test_texture_memory_bytes(
        self,
    ) -> None:
        self.assertEqual(
            texture_memory_bytes(
                1024,
                1024,
            ),
            (
                1024
                * 1024
                * 4
                * 4
            ),
        )

    def test_default_texture_memory_bytes(
        self,
    ) -> None:
        self.assertEqual(
            texture_memory_bytes(
                DEFAULT_TEXTURE_SIZE,
                DEFAULT_TEXTURE_SIZE,
            ),
            (
                512
                * 512
                * 4
                * 4
            ),
        )

    def test_texture_memory_rejects_negative_dimensions(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            texture_memory_bytes(
                -1,
                1024,
            )

    def test_coverage_statistics_are_consistent(
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
            result.stats.texture_pixels,
            16,
        )

        self.assertEqual(
            result.stats.filled_pixels,
            10,
        )

        self.assertEqual(
            result.stats.uncovered_pixels,
            6,
        )

        self.assertAlmostEqual(
            result.stats.coverage_ratio,
            10.0 / 16.0,
        )


# =========================================================
# Entry point
# =========================================================

if __name__ == "__main__":
    unittest.main()
