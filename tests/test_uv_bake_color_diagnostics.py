from tests.uv_bake_test_support import *

class UVBakeColorTests(
    unittest.TestCase
):
    def test_sampler_colors_are_clamped_by_default(
        self,
    ) -> None:
        result = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                constant_sampler(
                    (
                        -1.0,
                        2.0,
                        0.5,
                        3.0,
                    )
                ),
                config=UVBakeConfig(
                    width=1,
                    height=1,
                    padding_pixels=0,
                ),
            )
        )

        color = (
            result.texture.rgba(
                0,
                0,
            )
        )

        self.assertAlmostEqual(
            color[0],
            0.0,
        )

        self.assertAlmostEqual(
            color[1],
            1.0,
        )

        self.assertAlmostEqual(
            color[2],
            0.5,
        )

        self.assertAlmostEqual(
            color[3],
            1.0,
        )

    def test_clamping_can_be_disabled(
        self,
    ) -> None:
        result = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                constant_sampler(
                    (
                        -1.0,
                        2.0,
                        0.5,
                        3.0,
                    )
                ),
                config=UVBakeConfig(
                    width=1,
                    height=1,
                    padding_pixels=0,
                    clamp_colors=False,
                ),
            )
        )

        color = (
            result.texture.rgba(
                0,
                0,
            )
        )

        self.assertAlmostEqual(
            color[0],
            -1.0,
        )

        self.assertAlmostEqual(
            color[1],
            2.0,
        )

        self.assertAlmostEqual(
            color[2],
            0.5,
        )

        self.assertAlmostEqual(
            color[3],
            3.0,
        )

    def test_background_color_is_preserved_on_uncovered_pixels(
        self,
    ) -> None:
        background = (
            0.2,
            0.3,
            0.4,
            0.5,
        )

        result = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                constant_sampler(),
                config=UVBakeConfig(
                    width=2,
                    height=2,
                    padding_pixels=0,
                    background_color=(
                        background
                    ),
                ),
            )
        )

        color = (
            result.texture.rgba(
                1,
                1,
            )
        )

        for (
            actual,
            expected,
        ) in zip(
            color,
            background,
            strict=True,
        ):
            self.assertAlmostEqual(
                actual,
                expected,
                places=5,
            )


# =========================================================
# Diagnostics
# =========================================================

class UVBakeDiagnosticsTests(
    unittest.TestCase
):
    def test_surface_sample_statistics(
        self,
    ) -> None:
        def sampler(
            position,
            normal,
        ):
            return SurfaceColorSample(
                color=(
                    1.0,
                    0.0,
                    0.0,
                    1.0,
                ),
                used_fallback=True,
                selected_samples=2,
            )

        result = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                sampler,
                config=UVBakeConfig(
                    width=2,
                    height=2,
                    padding_pixels=0,
                ),
            )
        )

        self.assertEqual(
            result.stats.surface_samples,
            3,
        )

        self.assertEqual(
            result.stats.fallback_samples,
            3,
        )

        self.assertEqual(
            result.stats
            .selected_source_samples,
            6,
        )

    def test_degenerate_triangle_is_skipped(
        self,
    ) -> None:
        calls = 0

        triangle = UVBakeTriangle(
            a=vertex(
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            ),
            b=vertex(
                1.0,
                0.0,
                0.0,
                0.5,
                0.5,
            ),
            c=vertex(
                2.0,
                0.0,
                0.0,
                1.0,
                1.0,
            ),
        )

        def sampler(
            position,
            normal,
        ):
            nonlocal calls

            calls += 1

            return (
                1.0,
                0.0,
                0.0,
                1.0,
            )

        result = (
            bake_uv_texture(
                [
                    triangle
                ],
                sampler,
                config=UVBakeConfig(
                    width=8,
                    height=8,
                    padding_pixels=0,
                ),
            )
        )

        self.assertEqual(
            result.stats
            .degenerate_triangles,
            1,
        )

        self.assertEqual(
            result.stats
            .rasterized_triangles,
            0,
        )

        self.assertEqual(
            result.stats.covered_pixels,
            0,
        )

        self.assertEqual(
            calls,
            0,
        )

    def test_completely_outside_triangle_is_skipped(
        self,
    ) -> None:
        triangle = UVBakeTriangle(
            a=vertex(
                0.0,
                0.0,
                0.0,
                2.0,
                2.0,
            ),
            b=vertex(
                1.0,
                0.0,
                0.0,
                3.0,
                2.0,
            ),
            c=vertex(
                0.0,
                1.0,
                0.0,
                2.0,
                3.0,
            ),
        )

        result = (
            bake_uv_texture(
                [
                    triangle
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
            result.stats
            .outside_triangles,
            1,
        )

        self.assertEqual(
            result.stats
            .covered_pixels,
            0,
        )

    def test_partially_outside_triangle_is_reported_as_clipped(
        self,
    ) -> None:
        triangle = UVBakeTriangle(
            a=vertex(
                0.0,
                0.0,
                0.0,
                -0.25,
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

        result = (
            bake_uv_texture(
                [
                    triangle
                ],
                constant_sampler(),
                config=UVBakeConfig(
                    width=8,
                    height=8,
                    padding_pixels=0,
                ),
            )
        )

        self.assertEqual(
            result.stats
            .clipped_triangles,
            1,
        )

        self.assertGreater(
            result.stats
            .covered_pixels,
            0,
        )


# =========================================================
# Supersampling
# =========================================================
