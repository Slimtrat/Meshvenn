from __future__ import annotations

from tests.sdf_surface_test_support import *


class SDFSurfaceSphereTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.radius = 0.6

        self.volume = (
            sphere_volume(
                resolution=13,
                radius=(
                    self.radius
                ),
            )
        )

        self.result = (
            extract_surface_nets(
                self.volume
            )
        )

    def test_sphere_produces_surface(
        self,
    ) -> None:
        self.assertGreater(
            self.result
            .mesh
            .vertex_count,
            0,
        )

        self.assertGreater(
            self.result
            .mesh
            .polygon_count,
            0,
        )

    def test_sphere_is_closed_inside_grid(
        self,
    ) -> None:
        """
        Radius 0.6 stays far away from the normalized
        [-1,+1] domain boundary, so no crossing edge should
        require a missing outside cell.
        """

        stats = (
            self.result.stats
        )

        self.assertEqual(
            stats.skipped_boundary_edges,
            0,
        )

        self.assertEqual(
            stats.skipped_missing_cell_edges,
            0,
        )

        self.assertEqual(
            stats.crossing_grid_edges,
            stats.emitted_quads,
        )

    def test_axis_quad_counts_are_symmetric(
        self,
    ) -> None:
        stats = (
            self.result.stats
        )

        self.assertEqual(
            stats.emitted_x_quads,
            stats.emitted_y_quads,
        )

        self.assertEqual(
            stats.emitted_y_quads,
            stats.emitted_z_quads,
        )

        self.assertEqual(
            (
                stats.emitted_x_quads
                + stats.emitted_y_quads
                + stats.emitted_z_quads
            ),
            stats.emitted_quads,
        )

    def test_sphere_vertex_positions_follow_radius(
        self,
    ) -> None:
        """
        Surface Nets averages edge crossings, so positions are
        not analytically exact sphere samples.

        At resolution 13 they should nevertheless remain
        close to radius 0.6.
        """

        for vertex in (
            self.result.mesh.vertices
        ):
            radius = (
                vector_length(
                    vertex.position
                )
            )

            self.assertLess(
                abs(
                    radius
                    - self.radius
                ),
                0.05,
            )

    def test_sphere_normals_point_outward(
        self,
    ) -> None:
        for vertex in (
            self.result.mesh.vertices
        ):
            radial = normalized(
                vertex.position
            )

            alignment = dot3(
                radial,
                vertex.normal,
            )

            self.assertGreater(
                alignment,
                0.98,
            )

    def test_sphere_normals_are_unit_length(
        self,
    ) -> None:
        for vertex in (
            self.result.mesh.vertices
        ):
            self.assertAlmostEqual(
                vector_length(
                    vertex.normal
                ),
                1.0,
                places=4,
            )

    def test_sphere_face_winding_is_outward(
        self,
    ) -> None:
        for face in (
            self.result.mesh.faces
        ):
            normal = (
                face_geometric_normal(
                    self.result.mesh,
                    face,
                )
            )

            center = (
                face_center(
                    self.result.mesh,
                    face,
                )
            )

            self.assertGreater(
                dot3(
                    normal,
                    center,
                ),
                0.0,
            )

    def test_sphere_bounds_are_symmetric(
        self,
    ) -> None:
        bounds = (
            self.result.mesh.bounds
        )

        self.assertIsNotNone(
            bounds
        )

        minimum, maximum = (
            bounds
        )

        for axis in range(
            3
        ):
            self.assertAlmostEqual(
                minimum[axis],
                -maximum[axis],
                places=5,
            )

            self.assertLess(
                minimum[axis],
                -0.5,
            )

            self.assertGreater(
                minimum[axis],
                -0.65,
            )

            self.assertGreater(
                maximum[axis],
                0.5,
            )

            self.assertLess(
                maximum[axis],
                0.65,
            )
