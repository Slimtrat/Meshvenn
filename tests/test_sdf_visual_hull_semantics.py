from __future__ import annotations

from tests.sdf_test_support import *


class SDFVisualHullSemanticsTests(
    unittest.TestCase
):
    def test_hard_sdf_intersection_matches_boolean_logic(
        self,
    ) -> None:
        """
        With smoothness=0:

            fused <= 0

        must mean:

            every projection <= 0

        This is the continuous equivalent of the current
        Visual Hull silhouette intersection.
        """

        projections = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            ),

            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
            ),
        )

        points = (
            NormalizedPoint(
                x=0.0,
                y=0.0,
                z=0.0,
            ),

            NormalizedPoint(
                x=1.0,
                y=0.0,
                z=0.0,
            ),

            NormalizedPoint(
                x=0.0,
                y=1.0,
                z=0.0,
            ),

            NormalizedPoint(
                x=1.0,
                y=1.0,
                z=0.0,
            ),
        )

        for point in points:
            individual = [
                projection.sample(
                    point
                )
                for projection
                in projections
            ]

            fused = (
                sample_fused_sdf(
                    point,
                    projections,
                    smoothness=0.0,
                )
            )

            expected_inside = all(
                value <= 0.0
                for value
                in individual
            )

            actual_inside = (
                fused <= 0.0
            )

            self.assertEqual(
                actual_inside,
                expected_inside,
                msg=(
                    f"Point: {point}, "
                    f"individual={individual}, "
                    f"fused={fused}"
                ),
            )
