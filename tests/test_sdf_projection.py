from __future__ import annotations

from tests.sdf_test_support import *


class SDFProjectionTests(
    unittest.TestCase
):
    def test_front_projection_center_is_inside(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                name="Front",
            )
        )

        value = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=0.0,
                    z=0.0,
                )
            )
        )

        self.assertLess(
            value,
            0.0,
        )

    def test_front_projection_ignores_depth_axis(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        first = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=-1.0,
                    z=0.0,
                )
            )
        )

        second = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=1.0,
                    z=0.0,
                )
            )
        )

        self.assertAlmostEqual(
            first,
            second,
            places=6,
        )

    def test_front_projection_outside_x_is_positive(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        value = (
            projection.sample(
                NormalizedPoint(
                    x=1.0,
                    y=0.0,
                    z=0.0,
                )
            )
        )

        self.assertGreater(
            value,
            0.0,
        )

    def test_right_projection_constrains_y_axis(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                name="Right",
            )
        )

        center = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=0.0,
                    z=0.0,
                )
            )
        )

        outside = (
            projection.sample(
                NormalizedPoint(
                    x=0.0,
                    y=1.0,
                    z=0.0,
                )
            )
        )

        self.assertLess(
            center,
            0.0,
        )

        self.assertGreater(
            outside,
            0.0,
        )

    def test_from_source_view_uses_capabilities(
        self,
    ) -> None:
        view = SimpleNamespace(
            name="Synthetic",
            mask=(
                centered_square_mask()
            ),
            azimuth_degrees=45.0,
            elevation_degrees=10.0,
            flip_x=True,
        )

        projection = (
            SDFProjection
            .from_source_view(
                view
            )
        )

        self.assertEqual(
            projection.name,
            "Synthetic",
        )

        self.assertAlmostEqual(
            projection
            .transform
            .azimuth_degrees,
            45.0,
        )

        self.assertAlmostEqual(
            projection
            .transform
            .elevation_degrees,
            10.0,
        )

        self.assertTrue(
            projection
            .transform
            .flip_x
        )

    def test_build_sdf_projections(
        self,
    ) -> None:
        views = (
            SimpleNamespace(
                name="Front",
                mask=(
                    centered_square_mask()
                ),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                flip_x=False,
            ),
            SimpleNamespace(
                name="Right",
                mask=(
                    centered_square_mask()
                ),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                flip_x=False,
            ),
        )

        projections = (
            build_sdf_projections(
                views
            )
        )

        self.assertEqual(
            len(
                projections
            ),
            2,
        )

        self.assertEqual(
            projections[0].name,
            "Front",
        )

        self.assertEqual(
            projections[1].name,
            "Right",
        )
