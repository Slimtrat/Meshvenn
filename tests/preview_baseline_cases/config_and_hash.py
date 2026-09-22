from __future__ import annotations

from .support import *

class BaselineConfigTests(
    unittest.TestCase
):
    def test_valid_config_serializes(
        self,
    ) -> None:
        result = (
            DEFAULT_CONFIG
            .to_dict()
        )

        self.assertEqual(
            result,
            {
                "resolution": 64,
                "mesh_mode": (
                    "surface_nets"
                ),
                "material_mode": (
                    "projected-color-v1"
                ),
                "samples": 1,
                "turntable_views": 8,
                "render_size": 384,
                "renderer_version": 1,
            },
        )

    def test_invalid_resolution_rejected(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=0,
            mesh_mode="surface_nets",
            material_mode=(
                "projected-color-v1"
            ),
            samples=1,
            turntable_views=8,
            render_size=384,
        )

        with self.assertRaises(
            BaselineError
        ):
            config.validate()

    def test_invalid_mesh_mode_rejected(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=64,
            mesh_mode="magic",
            material_mode=(
                "projected-color-v1"
            ),
            samples=1,
            turntable_views=8,
            render_size=384,
        )

        with self.assertRaises(
            BaselineError
        ):
            config.validate()

    def test_empty_material_mode_rejected(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=64,
            mesh_mode="surface_nets",
            material_mode="",
            samples=1,
            turntable_views=8,
            render_size=384,
        )

        with self.assertRaises(
            BaselineError
        ):
            config.validate()

    def test_invalid_renderer_parameters_rejected(
        self,
    ) -> None:
        invalid_configs = [
            BaselineConfig(
                resolution=64,
                mesh_mode=(
                    "surface_nets"
                ),
                material_mode=(
                    "projected-color-v1"
                ),
                samples=0,
                turntable_views=8,
                render_size=384,
            ),
            BaselineConfig(
                resolution=64,
                mesh_mode=(
                    "surface_nets"
                ),
                material_mode=(
                    "projected-color-v1"
                ),
                samples=1,
                turntable_views=0,
                render_size=384,
            ),
            BaselineConfig(
                resolution=64,
                mesh_mode=(
                    "surface_nets"
                ),
                material_mode=(
                    "projected-color-v1"
                ),
                samples=1,
                turntable_views=8,
                render_size=0,
            ),
            BaselineConfig(
                resolution=64,
                mesh_mode=(
                    "surface_nets"
                ),
                material_mode=(
                    "projected-color-v1"
                ),
                samples=1,
                turntable_views=8,
                render_size=384,
                renderer_version=0,
            ),
        ]

        for config in invalid_configs:
            with self.subTest(
                config=config
            ):
                with self.assertRaises(
                    BaselineError
                ):
                    config.validate()


# ---------------------------------------------------------
# Hash tests
# ---------------------------------------------------------

class HashTests(
    unittest.TestCase
):
    def test_sha256_changes_with_content(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "sheet.png"
            )

            path.write_bytes(
                b"version-a"
            )

            first = sha256_file(
                path
            )

            path.write_bytes(
                b"version-b"
            )

            second = sha256_file(
                path
            )

            self.assertNotEqual(
                first,
                second,
            )

    def test_sha256_is_deterministic(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "sheet.png"
            )

            path.write_bytes(
                b"same-content"
            )

            self.assertEqual(
                sha256_file(
                    path
                ),
                sha256_file(
                    path
                ),
            )


# ---------------------------------------------------------
# Manifest generation tests
# ---------------------------------------------------------
