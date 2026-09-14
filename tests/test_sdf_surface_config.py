from __future__ import annotations

from tests.sdf_surface_test_support import *


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
