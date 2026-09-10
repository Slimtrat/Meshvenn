from __future__ import annotations

import math
import unittest

from array import array

from core.uv_bake import (
    MAX_PADDING_PIXELS,
    MAX_SAMPLES_PER_AXIS,
    MAX_TEXTURE_DIMENSION,
    SurfaceColorSample,
    TextureBuffer,
    UVBakeConfig,
    UVBakeTriangle,
    UVBakeVertex,
    bake_uv_texture,
    square_texture_config,
    texture_memory_bytes,
)


# =========================================================
# Helpers
# =========================================================

def vertex(
    x: float,
    y: float,
    z: float,
    u: float,
    v: float,
    *,
    normal: tuple[
        float,
        float,
        float,
    ] = (
        0.0,
        0.0,
        1.0,
    ),
) -> UVBakeVertex:
    return UVBakeVertex(
        position=(
            x,
            y,
            z,
        ),
        normal=normal,
        uv=(
            u,
            v,
        ),
    )


def unit_triangle(
    *,
    z: float = 0.0,
    source_index: int = 0,
) -> UVBakeTriangle:
    """
    UV triangle:

        (0,1)
          |
          |
          |\
          | \
          |  \
          |___\
        (0,0) (1,0)

    Position X/Y deliberately matches UV U/V.
    """

    return UVBakeTriangle(
        a=vertex(
            0.0,
            0.0,
            z,
            0.0,
            0.0,
        ),
        b=vertex(
            1.0,
            0.0,
            z,
            1.0,
            0.0,
        ),
        c=vertex(
            0.0,
            1.0,
            z,
            0.0,
            1.0,
        ),
        source_index=(
            source_index
        ),
    )


def reversed_unit_triangle(
) -> UVBakeTriangle:
    return UVBakeTriangle(
        a=vertex(
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ),
        b=vertex(
            0.0,
            1.0,
            0.0,
            0.0,
            1.0,
        ),
        c=vertex(
            1.0,
            0.0,
            0.0,
            1.0,
            0.0,
        ),
    )


def constant_sampler(
    color=(
        1.0,
        0.0,
        0.0,
        1.0,
    ),
):
    def sample(
        position,
        normal,
    ):
        return color

    return sample


# =========================================================
# UVBakeVertex
# =========================================================

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
                barycentric_epsilon=(
                    -0.1
                )
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

class UVBakeRasterizationTests(
    unittest.TestCase
):
    def test_unit_triangle_covers_three_pixels_in_2x2_texture(
        self,
    ) -> None:
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
                ),
            )
        )

        self.assertEqual(
            result.stats.covered_pixels,
            3,
        )

        self.assertEqual(
            result.stats
            .rasterized_triangles,
            1,
        )

        self.assertEqual(
            result.stats
            .degenerate_triangles,
            0,
        )

        self.assertEqual(
            result.stats
            .surface_samples,
            3,
        )

        self.assertTrue(
            result.is_covered(
                0,
                0,
            )
        )

        self.assertTrue(
            result.is_covered(
                1,
                0,
            )
        )

        self.assertTrue(
            result.is_covered(
                0,
                1,
            )
        )

        self.assertFalse(
            result.is_covered(
                1,
                1,
            )
        )

    def test_unit_triangle_covers_ten_pixels_in_4x4_texture(
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
            result.stats.covered_pixels,
            10,
        )

    def test_triangle_winding_does_not_change_coverage(
        self,
    ) -> None:
        config = UVBakeConfig(
            width=8,
            height=8,
            padding_pixels=0,
        )

        forward = (
            bake_uv_texture(
                [
                    unit_triangle()
                ],
                constant_sampler(),
                config=config,
            )
        )

        reversed_result = (
            bake_uv_texture(
                [
                    reversed_unit_triangle()
                ],
                constant_sampler(),
                config=config,
            )
        )

        self.assertEqual(
            forward.coverage,
            reversed_result.coverage,
        )

    def test_sampler_receives_interpolated_surface_position(
        self,
    ) -> None:
        def sampler(
            position,
            normal,
        ):
            return (
                position[0],
                position[1],
                0.0,
                1.0,
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

        # Pixel (0, 0) center is UV (0.25, 0.25).
        #
        # Since world X/Y deliberately matches U/V in the
        # unit triangle, the interpolated surface position
        # must also be (0.25, 0.25, 0).
        color = (
            result.texture.rgba(
                0,
                0,
            )
        )

        self.assertAlmostEqual(
            color[0],
            0.25,
            places=5,
        )

        self.assertAlmostEqual(
            color[1],
            0.25,
            places=5,
        )

        self.assertAlmostEqual(
            color[2],
            0.0,
            places=5,
        )

        self.assertAlmostEqual(
            color[3],
            1.0,
            places=5,
        )

    def test_interpolated_normal_is_normalized(
        self,
    ) -> None:
        captured_normals = []

        triangle = UVBakeTriangle(
            a=vertex(
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                normal=(
                    0.0,
                    0.0,
                    1.0,
                ),
            ),
            b=vertex(
                1.0,
                0.0,
                0.0,
                1.0,
                0.0,
                normal=(
                    0.0,
                    1.0,
                    1.0,
                ),
            ),
            c=vertex(
                0.0,
                1.0,
                0.0,
                0.0,
                1.0,
                normal=(
                    1.0,
                    0.0,
                    1.0,
                ),
            ),
        )

        def sampler(
            position,
            normal,
        ):
            captured_normals.append(
                normal
            )

            return (
                1.0,
                1.0,
                1.0,
                1.0,
            )

        bake_uv_texture(
            [
                triangle
            ],
            sampler,
            config=UVBakeConfig(
                width=2,
                height=2,
                padding_pixels=0,
            ),
        )

        self.assertTrue(
            captured_normals
        )

        for normal in (
            captured_normals
        ):
            length = math.sqrt(
                normal[0] ** 2
                + normal[1] ** 2
                + normal[2] ** 2
            )

            self.assertAlmostEqual(
                length,
                1.0,
                places=6,
            )


# =========================================================
# Color handling
# =========================================================

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

class UVBakePaddingTests(
    unittest.TestCase
):
    def test_one_pixel_island_gets_four_neighbours_with_padding_one(
        self,
    ) -> None:
        # Entire UV triangle lies inside texel (1, 1) of a
        # 4x4 texture.
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