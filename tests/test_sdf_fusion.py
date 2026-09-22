from __future__ import annotations

from tests.sdf_test_support import *


class SDFFusionTests(
    unittest.TestCase
):
    def test_hard_fusion_is_maximum(
        self,
    ) -> None:
        self.assertEqual(
            fuse_signed_distances(
                (
                    -0.5,
                    -0.2,
                    -0.8,
                )
            ),
            -0.2,
        )

        self.assertEqual(
            fuse_signed_distances(
                (
                    -0.5,
                    0.3,
                    -0.2,
                )
            ),
            0.3,
        )

    def test_intersection_requires_all_views_inside(
        self,
    ) -> None:
        front = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                name="Front",
            )
        )

        right = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                name="Right",
            )
        )

        projections = (
            front,
            right,
        )

        center = (
            sample_fused_sdf(
                NormalizedPoint(
                    x=0.0,
                    y=0.0,
                    z=0.0,
                ),
                projections,
            )
        )

        outside_front = (
            sample_fused_sdf(
                NormalizedPoint(
                    x=1.0,
                    y=0.0,
                    z=0.0,
                ),
                projections,
            )
        )

        outside_right = (
            sample_fused_sdf(
                NormalizedPoint(
                    x=0.0,
                    y=1.0,
                    z=0.0,
                ),
                projections,
            )
        )

        self.assertLess(
            center,
            0.0,
        )

        self.assertGreater(
            outside_front,
            0.0,
        )

        self.assertGreater(
            outside_right,
            0.0,
        )

    def test_smooth_max_equals_hard_max_outside_band(
        self,
    ) -> None:
        self.assertAlmostEqual(
            smooth_max(
                -2.0,
                1.0,
                0.5,
            ),
            1.0,
        )

    def test_smooth_max_rounds_equal_constraints(
        self,
    ) -> None:
        value = (
            smooth_max(
                0.0,
                0.0,
                1.0,
            )
        )

        self.assertAlmostEqual(
            value,
            0.25,
            places=6,
        )

    def test_smooth_max_is_commutative(
        self,
    ) -> None:
        a = (
            smooth_max(
                -0.2,
                0.1,
                0.5,
            )
        )

        b = (
            smooth_max(
                0.1,
                -0.2,
                0.5,
            )
        )

        self.assertAlmostEqual(
            a,
            b,
            places=8,
        )

    def test_negative_smoothness_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            smooth_max(
                0.0,
                0.0,
                -1.0,
            )

    def test_surface_offset_expands_field(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        point = NormalizedPoint(
            x=1.0,
            y=0.0,
            z=0.0,
        )

        base = (
            sample_fused_sdf(
                point,
                (
                    projection,
                ),
                surface_offset=0.0,
            )
        )

        expanded = (
            sample_fused_sdf(
                point,
                (
                    projection,
                ),
                surface_offset=0.25,
            )
        )

        self.assertAlmostEqual(
            expanded,
            base - 0.25,
            places=6,
        )


class SDFSymmetryTests(
    unittest.TestCase
):
    def test_symmetry_requires_mirrored_point_to_survive(
        self,
    ) -> None:
        mask = mask_from_rows(
            ".....",
            ".....",
            "##...",
            "##...",
            ".....",
        )

        projection = (
            SDFProjection.from_mask(
                mask,
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        # Deliberately place the point well inside the
        # asymmetric left-hand silhouette.
        #
        # Front projection:
        #
        #     x = -0.75 -> u = 0.125
        #     z =  0.00 -> v = 0.500
        #
        # This samples inside the two occupied rows instead
        # of interpolating across their lower boundary.
        #
        # Mirroring X produces:
        #
        #     x = +0.75 -> u = 0.875
        #
        # which is clearly outside the silhouette.
        point = NormalizedPoint(
            x=-0.75,
            y=0.0,
            z=0.0,
        )

        without_symmetry = (
            sample_fused_sdf(
                point,
                (
                    projection,
                ),
                symmetry_x=False,
            )
        )

        with_symmetry = (
            sample_fused_sdf(
                point,
                (
                    projection,
                ),
                symmetry_x=True,
            )
        )

        self.assertLess(
            without_symmetry,
            0.0,
        )

        self.assertGreater(
            with_symmetry,
            0.0,
        )
