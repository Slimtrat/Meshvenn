from tests.uv_bake_test_support import *

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
