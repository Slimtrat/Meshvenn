from __future__ import annotations

from tests.sdf_test_support import *


class SDFBuildConfigTests(
    unittest.TestCase
):
    def test_default_constants(
        self,
    ) -> None:
        self.assertEqual(
            DEFAULT_ISO_LEVEL,
            0.0,
        )

        self.assertEqual(
            DEFAULT_SMOOTHNESS,
            0.0,
        )

        self.assertEqual(
            DEFAULT_SURFACE_OFFSET,
            0.0,
        )

        self.assertFalse(
            DEFAULT_SYMMETRY_X
        )

    def test_valid_config(
        self,
    ) -> None:
        config = SDFBuildConfig(
            width=8,
            depth=9,
            height=10,
        )

        config.validate()

        self.assertEqual(
            config.dimensions,
            (
                8,
                9,
                10,
            ),
        )

        self.assertEqual(
            config.voxel_count,
            720,
        )

    def test_cubic_config(
        self,
    ) -> None:
        config = (
            cubic_sdf_config(
                16
            )
        )

        self.assertEqual(
            config.dimensions,
            (
                16,
                16,
                16,
            ),
        )

        self.assertEqual(
            config.voxel_count,
            4096,
        )

    def test_dimension_below_two_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            SDFBuildConfig(
                width=1,
                depth=8,
                height=8,
            ).validate()

    def test_negative_smoothness_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            SDFBuildConfig(
                width=8,
                depth=8,
                height=8,
                smoothness=-0.1,
            ).validate()

    def test_reference_volume_limit_is_enforced(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            SDFBuildConfig(
                width=10,
                depth=10,
                height=10,
                max_voxels=999,
            ).validate()
