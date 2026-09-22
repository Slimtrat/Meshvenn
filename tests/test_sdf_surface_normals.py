from __future__ import annotations

from tests.sdf_surface_test_support import *


class SDFSurfaceNormalTests(
    unittest.TestCase
):
    def test_x_plane_normal_points_positive_x(
        self,
    ) -> None:
        volume = (
            plane_x_volume(
                9
            )
        )

        normal = (
            estimate_sdf_normal(
                volume,
                (
                    0.0,
                    0.0,
                    0.0,
                ),
            )
        )

        self.assertAlmostEqual(
            normal[0],
            1.0,
            places=6,
        )

        self.assertAlmostEqual(
            normal[1],
            0.0,
            places=6,
        )

        self.assertAlmostEqual(
            normal[2],
            0.0,
            places=6,
        )

    def test_linear_field_gradient(
        self,
    ) -> None:
        volume = (
            analytic_volume(
                9,
                lambda x, y, z: (
                    x
                    + 2.0 * y
                    + 3.0 * z
                ),
            )
        )

        normal = (
            estimate_sdf_normal(
                volume,
                (
                    0.0,
                    0.0,
                    0.0,
                ),
            )
        )

        expected = normalized(
            (
                1.0,
                2.0,
                3.0,
            )
        )

        for index in range(
            3
        ):
            self.assertAlmostEqual(
                normal[index],
                expected[index],
                places=5,
            )

    def test_sphere_gradient_points_outward(
        self,
    ) -> None:
        volume = (
            sphere_volume(
                resolution=17,
                radius=0.6,
            )
        )

        point = (
            0.6,
            0.0,
            0.0,
        )

        normal = (
            estimate_sdf_normal(
                volume,
                point,
            )
        )

        self.assertGreater(
            normal[0],
            0.99,
        )

        self.assertAlmostEqual(
            normal[1],
            0.0,
            places=4,
        )

        self.assertAlmostEqual(
            normal[2],
            0.0,
            places=4,
        )

    def test_invalid_normal_step_is_rejected(
        self,
    ) -> None:
        volume = (
            plane_x_volume()
        )

        with self.assertRaises(
            ValueError
        ):
            estimate_sdf_normal(
                volume,
                (
                    0.0,
                    0.0,
                    0.0,
                ),
                step_scale=0.0,
            )
