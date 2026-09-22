from __future__ import annotations

from tests.sdf_test_support import *


class SDFBuildTests(
    unittest.TestCase
):
    def test_build_single_projection_volume(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                name="Front",
            )
        )

        config = (
            cubic_sdf_config(
                7
            )
        )

        result = (
            build_sdf_volume(
                (
                    projection,
                ),
                config=config,
            )
        )

        self.assertEqual(
            result.volume.dimensions,
            (
                7,
                7,
                7,
            ),
        )

        self.assertEqual(
            result.stats.voxel_count,
            343,
        )

        self.assertEqual(
            result.stats.projection_count,
            1,
        )

        self.assertEqual(
            result.stats
            .projection_sample_count,
            343,
        )

        self.assertTrue(
            result.volume
            .has_inside_samples
        )

        self.assertTrue(
            result.volume
            .has_outside_samples
        )

        self.assertTrue(
            result.volume
            .crosses_surface
        )

        self.assertLess(
            result.stats.minimum_distance,
            0.0,
        )

        self.assertGreater(
            result.stats.maximum_distance,
            0.0,
        )

    def test_two_projection_intersection_volume(
        self,
    ) -> None:
        projections = (
            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                name="Front",
            ),

            SDFProjection.from_mask(
                centered_large_square_mask(),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                name="Right",
            ),
        )

        result = (
            build_sdf_volume(
                projections,
                config=(
                    cubic_sdf_config(
                        7
                    )
                ),
            )
        )

        center = (
            result.volume.get(
                3,
                3,
                3,
            )
        )

        x_edge = (
            result.volume.get(
                6,
                3,
                3,
            )
        )

        y_edge = (
            result.volume.get(
                3,
                6,
                3,
            )
        )

        self.assertLess(
            center,
            0.0,
        )

        self.assertGreater(
            x_edge,
            0.0,
        )

        self.assertGreater(
            y_edge,
            0.0,
        )

        self.assertEqual(
            result.stats
            .projection_sample_count,
            (
                7
                * 7
                * 7
                * 2
            ),
        )

    def test_symmetry_doubles_projection_sampling_stats(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        result = (
            build_sdf_volume(
                (
                    projection,
                ),
                config=(
                    cubic_sdf_config(
                        5,
                        symmetry_x=True,
                    )
                ),
            )
        )

        self.assertEqual(
            result.stats
            .projection_sample_count,
            (
                5
                * 5
                * 5
                * 2
            ),
        )

    def test_progress_callback_runs_once_per_z_slice(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        progress = []

        result = (
            build_sdf_volume(
                (
                    projection,
                ),
                config=(
                    SDFBuildConfig(
                        width=5,
                        depth=6,
                        height=7,
                    )
                ),
                progress_callback=(
                    progress.append
                ),
            )
        )

        self.assertEqual(
            len(
                progress
            ),
            7,
        )

        self.assertEqual(
            progress[0]
            .completed_slices,
            1,
        )

        self.assertEqual(
            progress[-1]
            .completed_slices,
            7,
        )

        self.assertAlmostEqual(
            progress[-1]
            .fraction,
            1.0,
        )

        self.assertEqual(
            result.stats.voxel_count,
            (
                5
                * 6
                * 7
            ),
        )

    def test_build_from_source_views(
        self,
    ) -> None:
        views = (
            SimpleNamespace(
                name="Front",
                mask=(
                    centered_large_square_mask()
                ),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
                flip_x=False,
            ),

            SimpleNamespace(
                name="Right",
                mask=(
                    centered_large_square_mask()
                ),
                azimuth_degrees=90.0,
                elevation_degrees=0.0,
                flip_x=False,
            ),
        )

        result = (
            build_sdf_from_views(
                views,
                config=(
                    cubic_sdf_config(
                        5
                    )
                ),
            )
        )

        self.assertEqual(
            len(
                result.projections
            ),
            2,
        )

        self.assertEqual(
            result.stats
            .projection_count,
            2,
        )

        self.assertTrue(
            result.volume
            .crosses_surface
        )

    def test_sample_classification_counts_match_volume(
        self,
    ) -> None:
        projection = (
            SDFProjection.from_mask(
                centered_square_mask(),
                azimuth_degrees=0.0,
                elevation_degrees=0.0,
            )
        )

        result = (
            build_sdf_volume(
                (
                    projection,
                ),
                config=(
                    cubic_sdf_config(
                        5
                    )
                ),
            )
        )

        classified = (
            result.stats.negative_samples
            + result.stats.zero_samples
            + result.stats.positive_samples
        )

        self.assertEqual(
            classified,
            result.stats.voxel_count,
        )
