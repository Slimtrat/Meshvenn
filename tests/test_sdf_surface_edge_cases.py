from __future__ import annotations

from tests.sdf_surface_test_support import *


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
