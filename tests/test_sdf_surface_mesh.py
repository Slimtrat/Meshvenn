from __future__ import annotations

from tests.sdf_surface_test_support import *


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
