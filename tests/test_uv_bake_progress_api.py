from tests.uv_bake_test_support import *

class UVBakeProgressTests(
    unittest.TestCase
):
    def test_progress_callback_runs_once_per_triangle(
        self,
    ) -> None:
        progress = []

        triangles = (
            unit_triangle(
                z=0.0
            ),
            unit_triangle(
                z=1.0
            ),
        )

        result = (
            bake_uv_texture(
                triangles,
                constant_sampler(),
                config=UVBakeConfig(
                    width=2,
                    height=2,
                    padding_pixels=0,
                ),
                progress_callback=(
                    lambda event:
                    progress.append(
                        event
                    )
                ),
            )
        )

        self.assertEqual(
            result.stats.triangle_count,
            2,
        )

        self.assertEqual(
            len(
                progress
            ),
            2,
        )

        self.assertEqual(
            progress[0]
            .completed_triangles,
            1,
        )

        self.assertEqual(
            progress[0]
            .total_triangles,
            2,
        )

        self.assertAlmostEqual(
            progress[0].fraction,
            0.5,
        )

        self.assertAlmostEqual(
            progress[1].fraction,
            1.0,
        )


# =========================================================
# Public API validation
# =========================================================

class UVBakePublicApiTests(
    unittest.TestCase
):
    def test_empty_triangle_collection_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            bake_uv_texture(
                [],
                constant_sampler(),
            )

    def test_invalid_triangle_type_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            bake_uv_texture(
                [
                    "not-a-triangle"
                ],
                constant_sampler(),
            )

    def test_non_callable_sampler_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                None,
            )

    def test_non_callable_progress_callback_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                constant_sampler(),
                progress_callback=123,
            )

    def test_generator_input_is_supported(
        self,
    ) -> None:
        triangles = (
            unit_triangle(
                z=float(
                    index
                )
            )
            for index
            in range(
                2
            )
        )

        result = (
            bake_uv_texture(
                triangles,
                constant_sampler(),
                config=UVBakeConfig(
                    width=2,
                    height=2,
                    padding_pixels=0,
                ),
            )
        )

        self.assertEqual(
            result.stats.triangle_count,
            2,
        )


# =========================================================
# Convenience helpers
# =========================================================
