from __future__ import annotations

from tests.sdf_surface_test_support import *


class SDFSurfaceStatsTests(
    unittest.TestCase
):
    def test_plane_statistics(
        self,
    ) -> None:
        result = (
            extract_surface_nets(
                plane_x_volume(
                    7
                ),
                config=(
                    SDFSurfaceConfig(
                        iso_level=0.17
                    )
                ),
            )
        )

        stats = (
            result.stats
        )

        # 6 × 6 × 6 scalar-grid cells.
        self.assertEqual(
            stats.cell_count,
            216,
        )

        # One X-layer of cells is active:
        #
        #     6 × 6
        self.assertEqual(
            stats.active_cells,
            36,
        )

        self.assertEqual(
            stats.unique_cell_intersections,
            (
                36
                * 4
            ),
        )

        # There are 7 × 7 X grid edges crossing the plane.
        self.assertEqual(
            stats.crossing_grid_edges,
            49,
        )

        # Interior grid edges become:
        #
        #     5 × 5 quads
        self.assertEqual(
            stats.emitted_quads,
            25,
        )

        self.assertEqual(
            stats.emitted_x_quads,
            25,
        )

        self.assertEqual(
            stats.emitted_y_quads,
            0,
        )

        self.assertEqual(
            stats.emitted_z_quads,
            0,
        )

        self.assertEqual(
            stats.skipped_boundary_edges,
            24,
        )

        self.assertEqual(
            stats.skipped_missing_cell_edges,
            0,
        )

    def test_active_cell_ratio(
        self,
    ) -> None:
        result = (
            extract_surface_nets(
                plane_x_volume(
                    7
                ),
                config=(
                    SDFSurfaceConfig(
                        iso_level=0.17
                    )
                ),
            )
        )

        self.assertAlmostEqual(
            result
            .stats
            .active_cell_ratio,
            (
                36.0
                / 216.0
            ),
        )
