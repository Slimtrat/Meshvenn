from __future__ import annotations

from tests.sdf_surface_test_support import *


class SDFSurfacePlaneTests(
    unittest.TestCase
):
    def test_plane_is_extracted_at_subvoxel_position(
        self,
    ) -> None:
        """
        Resolution 7 grid X coordinates:

            -1
            -0.666...
            -0.333...
             0
             0.333...
             0.666...
             1

        x = 0.17 is therefore deliberately NOT a grid
        coordinate.

        Surface Nets should interpolate it exactly rather than
        snap to 0 or 0.333...
        """

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

        self.assertFalse(
            result.mesh.empty
        )

        self.assertEqual(
            result.mesh.vertex_count,
            36,
        )

        self.assertEqual(
            result.mesh.quad_count,
            25,
        )

        for vertex in (
            result.mesh.vertices
        ):
            self.assertAlmostEqual(
                vertex.position[0],
                0.17,
                places=6,
            )

    def test_plane_vertices_are_inside_source_cells(
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

        for vertex in (
            result.mesh.vertices
        ):
            (
                cell_x,
                cell_y,
                cell_z,
            ) = vertex.cell

            minimum_x = (
                grid_to_normalized(
                    cell_x,
                    7,
                )
            )

            maximum_x = (
                grid_to_normalized(
                    cell_x + 1,
                    7,
                )
            )

            self.assertGreaterEqual(
                vertex.position[0],
                minimum_x,
            )

            self.assertLessEqual(
                vertex.position[0],
                maximum_x,
            )

            self.assertGreaterEqual(
                vertex.position[1],
                -1.0,
            )

            self.assertLessEqual(
                vertex.position[1],
                1.0,
            )

            self.assertGreaterEqual(
                vertex.position[2],
                -1.0,
            )

            self.assertLessEqual(
                vertex.position[2],
                1.0,
            )

    def test_planar_cell_has_four_unique_intersections(
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

        for vertex in (
            result.mesh.vertices
        ):
            self.assertEqual(
                vertex.intersection_count,
                4,
            )

    def test_plane_normals_are_positive_x(
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

        for vertex in (
            result.mesh.vertices
        ):
            self.assertGreater(
                vertex.normal[0],
                0.999,
            )

            self.assertAlmostEqual(
                vertex.normal[1],
                0.0,
                places=5,
            )

            self.assertAlmostEqual(
                vertex.normal[2],
                0.0,
                places=5,
            )

    def test_plane_face_winding_points_outward(
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

        for face in (
            result.mesh.faces
        ):
            normal = (
                face_geometric_normal(
                    result.mesh,
                    face,
                )
            )

            self.assertGreater(
                normal[0],
                0.999,
            )

    def test_reverse_field_reverses_face_winding(
        self,
    ) -> None:
        """
        Field:

            d = -x

        has outside direction toward -X.
        """

        volume = (
            analytic_volume(
                7,
                lambda x, y, z: (
                    -x
                ),
            )
        )

        result = (
            extract_surface_nets(
                volume,
                config=(
                    SDFSurfaceConfig(
                        iso_level=-0.17
                    )
                ),
            )
        )

        for face in (
            result.mesh.faces
        ):
            normal = (
                face_geometric_normal(
                    result.mesh,
                    face,
                )
            )

            self.assertLess(
                normal[0],
                -0.999,
            )

    def test_iso_level_moves_surface_continuously(
        self,
    ) -> None:
        """
        The same scalar grid is extracted twice.

        A binary occupancy mesher would generally snap both
        versions to voxel boundaries.

        Continuous Surface Nets must follow the scalar iso
        value exactly.
        """

        volume = (
            plane_x_volume(
                7
            )
        )

        first = (
            extract_surface_nets(
                volume,
                config=(
                    SDFSurfaceConfig(
                        iso_level=-0.23
                    )
                ),
            )
        )

        second = (
            extract_surface_nets(
                volume,
                config=(
                    SDFSurfaceConfig(
                        iso_level=0.17
                    )
                ),
            )
        )

        first_x = {
            round(
                vertex.position[0],
                6,
            )
            for vertex
            in first.mesh.vertices
        }

        second_x = {
            round(
                vertex.position[0],
                6,
            )
            for vertex
            in second.mesh.vertices
        }

        self.assertEqual(
            first_x,
            {
                -0.23
            },
        )

        self.assertEqual(
            second_x,
            {
                0.17
            },
        )

        self.assertAlmostEqual(
            (
                next(
                    iter(
                        second_x
                    )
                )
                - next(
                    iter(
                        first_x
                    )
                )
            ),
            0.40,
            places=6,
        )

    def test_volume_iso_level_is_respected(
        self,
    ) -> None:
        volume = (
            analytic_volume(
                7,
                lambda x, y, z: x,
                iso_level=0.21,
            )
        )

        result = (
            extract_surface_nets(
                volume
            )
        )

        for vertex in (
            result.mesh.vertices
        ):
            self.assertAlmostEqual(
                vertex.position[0],
                0.21,
                places=6,
            )

        self.assertAlmostEqual(
            result.mesh.iso_level,
            0.21,
        )

    def test_explicit_iso_overrides_volume_iso(
        self,
    ) -> None:
        volume = (
            analytic_volume(
                7,
                lambda x, y, z: x,
                iso_level=0.21,
            )
        )

        result = (
            extract_surface_nets(
                volume,
                config=(
                    SDFSurfaceConfig(
                        iso_level=-0.19
                    )
                ),
            )
        )

        for vertex in (
            result.mesh.vertices
        ):
            self.assertAlmostEqual(
                vertex.position[0],
                -0.19,
                places=6,
            )
