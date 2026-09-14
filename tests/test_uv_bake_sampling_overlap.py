from tests.uv_bake_test_support import *

class UVBakeSupersamplingTests(
    unittest.TestCase
):
    def test_supersampling_performs_more_surface_samples(
        self,
    ) -> None:
        single = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                constant_sampler(),
                config=UVBakeConfig(
                    width=8,
                    height=8,
                    padding_pixels=0,
                    samples_per_axis=1,
                ),
            )
        )

        supersampled = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                constant_sampler(),
                config=UVBakeConfig(
                    width=8,
                    height=8,
                    padding_pixels=0,
                    samples_per_axis=2,
                ),
            )
        )

        self.assertGreater(
            supersampled.stats
            .surface_samples,
            single.stats
            .surface_samples,
        )

    def test_surface_samples_match_sampler_invocations(
        self,
    ) -> None:
        calls = 0

        def sampler(
            position,
            normal,
        ):
            nonlocal calls

            calls += 1

            return (
                1.0,
                1.0,
                1.0,
                1.0,
            )

        result = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                sampler,
                config=UVBakeConfig(
                    width=8,
                    height=8,
                    padding_pixels=0,
                    samples_per_axis=3,
                ),
            )
        )

        self.assertEqual(
            calls,
            result.stats.surface_samples,
        )


# =========================================================
# UV overlap
# =========================================================

class UVBakeOverlapTests(
    unittest.TestCase
):
    def test_identical_uv_triangles_report_overlap(
        self,
    ) -> None:
        first = unit_triangle(
            z=0.0,
            source_index=0,
        )

        second = unit_triangle(
            z=1.0,
            source_index=1,
        )

        def sampler(
            position,
            normal,
        ):
            if position[2] < 0.5:
                return (
                    1.0,
                    0.0,
                    0.0,
                    1.0,
                )

            return (
                0.0,
                0.0,
                1.0,
                1.0,
            )

        result = (
            bake_uv_texture(
                [
                    first,
                    second,
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
            result.stats.covered_pixels,
            3,
        )

        self.assertEqual(
            result.stats.overlap_pixels,
            3,
        )

        self.assertEqual(
            result.stats.surface_samples,
            6,
        )

    def test_exact_overlap_tie_preserves_first_triangle(
        self,
    ) -> None:
        first = unit_triangle(
            z=0.0
        )

        second = unit_triangle(
            z=1.0
        )

        def sampler(
            position,
            normal,
        ):
            if position[2] < 0.5:
                return (
                    1.0,
                    0.0,
                    0.0,
                    1.0,
                )

            return (
                0.0,
                0.0,
                1.0,
                1.0,
            )

        result = (
            bake_uv_texture(
                [
                    first,
                    second,
                ],
                sampler,
                config=UVBakeConfig(
                    width=2,
                    height=2,
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
            1.0,
        )

        self.assertAlmostEqual(
            color[1],
            0.0,
        )

        self.assertAlmostEqual(
            color[2],
            0.0,
        )


# =========================================================
# Padding
# =========================================================
