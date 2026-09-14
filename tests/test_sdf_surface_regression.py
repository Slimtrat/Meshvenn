from __future__ import annotations

from tests.sdf_surface_test_support import *


class SDFSurfaceContinuousRegressionTests(
    unittest.TestCase
):
    def test_surface_position_is_not_quantized_to_grid(
        self,
    ) -> None:
        resolution = 7

        iso = 0.173

        grid_positions = {
            round(
                grid_to_normalized(
                    index,
                    resolution,
                ),
                6,
            )
            for index
            in range(
                resolution
            )
        }

        self.assertNotIn(
            round(
                iso,
                6,
            ),
            grid_positions,
        )

        result = (
            extract_surface_nets(
                plane_x_volume(
                    resolution
                ),
                config=(
                    SDFSurfaceConfig(
                        iso_level=iso
                    )
                ),
            )
        )

        extracted_x = {
            round(
                vertex.position[0],
                6,
            )
            for vertex
            in result.mesh.vertices
        }

        self.assertEqual(
            extracted_x,
            {
                round(
                    iso,
                    6,
                )
            },
        )

    def test_small_iso_change_moves_vertices_by_small_amount(
        self,
    ) -> None:
        volume = (
            plane_x_volume(
                7
            )
        )

        first_iso = 0.171

        second_iso = 0.179

        first = (
            extract_surface_nets(
                volume,
                config=(
                    SDFSurfaceConfig(
                        iso_level=first_iso
                    )
                ),
            )
        )

        second = (
            extract_surface_nets(
                volume,
                config=(
                    SDFSurfaceConfig(
                        iso_level=second_iso
                    )
                ),
            )
        )

        self.assertEqual(
            first.mesh.vertex_count,
            second.mesh.vertex_count,
        )

        self.assertEqual(
            first.mesh.faces,
            second.mesh.faces,
        )

        for (
            first_vertex,
            second_vertex,
        ) in zip(
            first.mesh.vertices,
            second.mesh.vertices,
            strict=True,
        ):
            self.assertAlmostEqual(
                (
                    second_vertex
                    .position[0]
                    - first_vertex
                    .position[0]
                ),
                (
                    second_iso
                    - first_iso
                ),
                places=6,
            )

            self.assertAlmostEqual(
                first_vertex.position[1],
                second_vertex.position[1],
                places=6,
            )

            self.assertAlmostEqual(
                first_vertex.position[2],
                second_vertex.position[2],
                places=6,
            )
