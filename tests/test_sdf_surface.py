from __future__ import annotations

import math
import unittest

from array import array

from core.projection_math import (
    grid_to_normalized,
)
from core.sdf import (
    SDFVolume,
)
from core.sdf_surface import (
    DEFAULT_GENERATE_NORMALS,
    DEFAULT_GRADIENT_STEP_SCALE,
    SDFSurfaceConfig,
    SDFSurfaceMesh,
    SDFSurfaceVertex,
    estimate_sdf_normal,
    extract_surface_nets,
)


# =========================================================
# Helpers
# =========================================================

def analytic_volume(
    resolution: int,
    function,
    *,
    iso_level: float = 0.0,
) -> SDFVolume:
    """
    Sample an analytic scalar field on the exact normalized
    Meshvenn reconstruction grid:

        index 0              -> -1
        index resolution - 1 -> +1
    """

    values = array(
        "f"
    )

    for z in range(
        resolution
    ):
        nz = (
            grid_to_normalized(
                z,
                resolution,
            )
        )

        for y in range(
            resolution
        ):
            ny = (
                grid_to_normalized(
                    y,
                    resolution,
                )
            )

            for x in range(
                resolution
            ):
                nx = (
                    grid_to_normalized(
                        x,
                        resolution,
                    )
                )

                values.append(
                    float(
                        function(
                            nx,
                            ny,
                            nz,
                        )
                    )
                )

    return SDFVolume(
        width=resolution,
        depth=resolution,
        height=resolution,
        values=values,
        iso_level=iso_level,
    )


def plane_x_volume(
    resolution: int = 7,
) -> SDFVolume:
    """
    Exact analytic field:

        d(x, y, z) = x

    Any iso-level therefore produces the plane:

        x = iso
    """

    return analytic_volume(
        resolution,
        lambda x, y, z: x,
    )


def sphere_volume(
    *,
    resolution: int = 13,
    radius: float = 0.6,
) -> SDFVolume:
    """
    Exact analytic sphere SDF sampled on the grid.
    """

    return analytic_volume(
        resolution,
        lambda x, y, z: (
            math.sqrt(
                x * x
                + y * y
                + z * z
            )
            - radius
        ),
    )


def vector_length(
    value,
) -> float:
    return math.sqrt(
        value[0] * value[0]
        + value[1] * value[1]
        + value[2] * value[2]
    )


def dot3(
    first,
    second,
) -> float:
    return (
        first[0]
        * second[0]
        + first[1]
        * second[1]
        + first[2]
        * second[2]
    )


def subtract3(
    first,
    second,
):
    return (
        first[0]
        - second[0],

        first[1]
        - second[1],

        first[2]
        - second[2],
    )


def cross3(
    first,
    second,
):
    return (
        first[1]
        * second[2]
        - first[2]
        * second[1],

        first[2]
        * second[0]
        - first[0]
        * second[2],

        first[0]
        * second[1]
        - first[1]
        * second[0],
    )


def normalized(
    value,
):
    length = vector_length(
        value
    )

    if length <= 1e-12:
        return (
            0.0,
            0.0,
            0.0,
        )

    return (
        value[0]
        / length,

        value[1]
        / length,

        value[2]
        / length,
    )


def face_geometric_normal(
    mesh: SDFSurfaceMesh,
    face,
):
    first = (
        mesh.vertices[
            face[0]
        ].position
    )

    second = (
        mesh.vertices[
            face[1]
        ].position
    )

    third = (
        mesh.vertices[
            face[2]
        ].position
    )

    edge_a = subtract3(
        second,
        first,
    )

    edge_b = subtract3(
        third,
        first,
    )

    return normalized(
        cross3(
            edge_a,
            edge_b,
        )
    )


def face_center(
    mesh: SDFSurfaceMesh,
    face,
):
    points = [
        mesh.vertices[
            index
        ].position
        for index
        in face
    ]

    return (
        sum(
            value[0]
            for value
            in points
        )
        / 4.0,

        sum(
            value[1]
            for value
            in points
        )
        / 4.0,

        sum(
            value[2]
            for value
            in points
        )
        / 4.0,
    )


# =========================================================
# Configuration
# =========================================================

class SDFSurfaceConfigTests(
    unittest.TestCase
):
    def test_defaults(
        self,
    ) -> None:
        config = (
            SDFSurfaceConfig()
        )

        self.assertIsNone(
            config.iso_level
        )

        self.assertAlmostEqual(
            config.gradient_step_scale,
            DEFAULT_GRADIENT_STEP_SCALE,
        )

        self.assertEqual(
            config.generate_normals,
            DEFAULT_GENERATE_NORMALS,
        )

        config.validate()

    def test_volume_iso_level_is_used_by_default(
        self,
    ) -> None:
        volume = SDFVolume(
            width=2,
            depth=2,
            height=2,
            values=array(
                "f",
                (
                    -1.0,
                    1.0,
                    -1.0,
                    1.0,
                    -1.0,
                    1.0,
                    -1.0,
                    1.0,
                ),
            ),
            iso_level=0.25,
        )

        config = (
            SDFSurfaceConfig()
        )

        self.assertAlmostEqual(
            config.resolved_iso_level(
                volume
            ),
            0.25,
        )

    def test_explicit_iso_overrides_volume(
        self,
    ) -> None:
        volume = (
            plane_x_volume()
        )

        config = (
            SDFSurfaceConfig(
                iso_level=-0.3
            )
        )

        self.assertAlmostEqual(
            config.resolved_iso_level(
                volume
            ),
            -0.3,
        )

    def test_non_finite_iso_is_rejected(
        self,
    ) -> None:
        for value in (
            math.nan,
            math.inf,
            -math.inf,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    SDFSurfaceConfig(
                        iso_level=value
                    ).validate()

    def test_invalid_gradient_step_is_rejected(
        self,
    ) -> None:
        for value in (
            0.0,
            -1.0,
            math.nan,
            math.inf,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    SDFSurfaceConfig(
                        gradient_step_scale=(
                            value
                        )
                    ).validate()


# =========================================================
# Analytic normals
# =========================================================

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


# =========================================================
# Exact sub-voxel plane extraction
# =========================================================

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


# =========================================================
# Sphere extraction
# =========================================================

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


# =========================================================
# Empty / constant fields
# =========================================================

class SDFSurfaceEmptyTests(
    unittest.TestCase
):
    def test_all_positive_field_produces_empty_mesh(
        self,
    ) -> None:
        volume = (
            analytic_volume(
                5,
                lambda x, y, z: 1.0,
            )
        )

        result = (
            extract_surface_nets(
                volume
            )
        )

        self.assertTrue(
            result.mesh.empty
        )

        self.assertEqual(
            result.mesh.vertex_count,
            0,
        )

        self.assertEqual(
            result.mesh.polygon_count,
            0,
        )

        self.assertEqual(
            result.stats.active_cells,
            0,
        )

    def test_all_negative_field_produces_empty_mesh(
        self,
    ) -> None:
        volume = (
            analytic_volume(
                5,
                lambda x, y, z: -1.0,
            )
        )

        result = (
            extract_surface_nets(
                volume
            )
        )

        self.assertTrue(
            result.mesh.empty
        )

        self.assertEqual(
            result.stats
            .crossing_grid_edges,
            0,
        )

    def test_wrong_volume_type_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            extract_surface_nets(
                object()
            )

    def test_wrong_config_type_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            TypeError
        ):
            extract_surface_nets(
                plane_x_volume(),
                config=object(),
            )


# =========================================================
# Normals disabled
# =========================================================

class SDFSurfaceNormalsDisabledTests(
    unittest.TestCase
):
    def test_normal_generation_can_be_disabled(
        self,
    ) -> None:
        result = (
            extract_surface_nets(
                plane_x_volume(),
                config=(
                    SDFSurfaceConfig(
                        iso_level=0.17,
                        generate_normals=False,
                    )
                ),
            )
        )

        for vertex in (
            result.mesh.vertices
        ):
            self.assertEqual(
                vertex.normal,
                (
                    0.0,
                    0.0,
                    0.0,
                ),
            )


# =========================================================
# Mesh contract
# =========================================================

class SDFSurfaceMeshTests(
    unittest.TestCase
):
    def test_properties(
        self,
    ) -> None:
        result = (
            extract_surface_nets(
                plane_x_volume(),
                config=(
                    SDFSurfaceConfig(
                        iso_level=0.17
                    )
                ),
            )
        )

        mesh = (
            result.mesh
        )

        self.assertEqual(
            mesh.polygon_count,
            mesh.quad_count,
        )

        self.assertEqual(
            mesh.triangle_count,
            (
                mesh.quad_count
                * 2
            ),
        )

        self.assertEqual(
            mesh.index_count,
            (
                mesh.quad_count
                * 4
            ),
        )

        self.assertEqual(
            len(
                mesh.positions
            ),
            mesh.vertex_count,
        )

        self.assertEqual(
            len(
                mesh.normals
            ),
            mesh.vertex_count,
        )

    def test_all_faces_have_four_unique_indices(
        self,
    ) -> None:
        result = (
            extract_surface_nets(
                sphere_volume()
            )
        )

        vertex_count = (
            result
            .mesh
            .vertex_count
        )

        for face in (
            result.mesh.faces
        ):
            self.assertEqual(
                len(
                    face
                ),
                4,
            )

            self.assertEqual(
                len(
                    set(
                        face
                    )
                ),
                4,
            )

            for index in face:
                self.assertGreaterEqual(
                    index,
                    0,
                )

                self.assertLess(
                    index,
                    vertex_count,
                )

    def test_triangulation_produces_two_triangles_per_quad(
        self,
    ) -> None:
        result = (
            extract_surface_nets(
                sphere_volume()
            )
        )

        triangles = (
            result
            .mesh
            .triangulated_faces()
        )

        self.assertEqual(
            len(
                triangles
            ),
            (
                result
                .mesh
                .quad_count
                * 2
            ),
        )

        for triangle in (
            triangles
        ):
            self.assertEqual(
                len(
                    triangle
                ),
                3,
            )

    def test_invalid_face_index_is_rejected(
        self,
    ) -> None:
        vertex = (
            SDFSurfaceVertex(
                position=(
                    0.0,
                    0.0,
                    0.0,
                ),
                normal=(
                    1.0,
                    0.0,
                    0.0,
                ),
                cell=(
                    0,
                    0,
                    0,
                ),
                intersection_count=1,
            )
        )

        with self.assertRaises(
            ValueError
        ):
            SDFSurfaceMesh(
                vertices=(
                    vertex,
                ),

                faces=(
                    (
                        0,
                        1,
                        2,
                        3,
                    ),
                ),

                source_dimensions=(
                    2,
                    2,
                    2,
                ),

                iso_level=0.0,
            )

    def test_duplicate_face_indices_are_rejected(
        self,
    ) -> None:
        vertices = tuple(
            SDFSurfaceVertex(
                position=(
                    float(index),
                    0.0,
                    0.0,
                ),
                normal=(
                    1.0,
                    0.0,
                    0.0,
                ),
                cell=(
                    index,
                    0,
                    0,
                ),
                intersection_count=1,
            )
            for index
            in range(
                4
            )
        )

        with self.assertRaises(
            ValueError
        ):
            SDFSurfaceMesh(
                vertices=vertices,

                faces=(
                    (
                        0,
                        1,
                        1,
                        3,
                    ),
                ),

                source_dimensions=(
                    5,
                    2,
                    2,
                ),

                iso_level=0.0,
            )


# =========================================================
# Statistics
# =========================================================

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


# =========================================================
# Continuous surface regression
# =========================================================

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


# =========================================================
# Entry point
# =========================================================

if __name__ == "__main__":
    unittest.main()