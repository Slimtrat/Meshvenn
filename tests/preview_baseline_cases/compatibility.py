from __future__ import annotations

from .support import *

class CompatibilityTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.repository = (
            TemporaryBaselineRepository()
        )

        self.manifest = (
            self.repository.manifest()
        )

    def tearDown(
        self,
    ) -> None:
        self.repository.close()

    def check(
        self,
        *,
        manifest: dict | None = None,
        source: Path | None = None,
        sheet: str = "sheet1",
        profile: str = "L10",
        config: BaselineConfig = (
            DEFAULT_CONFIG
        ),
    ):
        return check_compatibility(
            (
                manifest
                if manifest is not None
                else self.manifest
            ),
            sheet_name=sheet,
            source_path=(
                source
                if source is not None
                else self.repository.sheet1
            ),
            profile=profile,
            expected_config=config,
        )

    def test_matching_baseline_is_compatible(
        self,
    ) -> None:
        result = self.check()

        self.assertTrue(
            result.compatible
        )

        self.assertEqual(
            result.reason,
            "compatible",
        )

    def test_schema_change_invalidates_baseline(
        self,
    ) -> None:
        manifest = dict(
            self.manifest
        )

        manifest[
            "schema_version"
        ] = (
            SCHEMA_VERSION
            + 1
        )

        result = self.check(
            manifest=manifest
        )

        self.assertFalse(
            result.compatible
        )

        self.assertEqual(
            result.reason,
            "schema-version-mismatch",
        )

    def test_resolution_change_invalidates_baseline(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=128,
            mesh_mode="surface_nets",
            material_mode=(
                "projected-color-v1"
            ),
            samples=1,
            turntable_views=8,
            render_size=384,
        )

        result = self.check(
            config=config
        )

        self.assertFalse(
            result.compatible
        )

        self.assertIn(
            "configuration-mismatch:resolution",
            result.reason,
        )

    def test_mesh_mode_change_invalidates_baseline(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=64,
            mesh_mode="blocks",
            material_mode=(
                "projected-color-v1"
            ),
            samples=1,
            turntable_views=8,
            render_size=384,
        )

        result = self.check(
            config=config
        )

        self.assertFalse(
            result.compatible
        )

        self.assertIn(
            "configuration-mismatch:mesh_mode",
            result.reason,
        )

    def test_material_mode_change_invalidates_baseline(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=64,
            mesh_mode="surface_nets",
            material_mode=(
                "projected-color-v2"
            ),
            samples=1,
            turntable_views=8,
            render_size=384,
        )

        result = self.check(
            config=config
        )

        self.assertFalse(
            result.compatible
        )

        self.assertIn(
            "configuration-mismatch:material_mode",
            result.reason,
        )

    def test_renderer_version_change_invalidates_baseline(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=64,
            mesh_mode="surface_nets",
            material_mode=(
                "projected-color-v1"
            ),
            samples=1,
            turntable_views=8,
            render_size=384,
            renderer_version=2,
        )

        result = self.check(
            config=config
        )

        self.assertFalse(
            result.compatible
        )

        self.assertIn(
            "configuration-mismatch:renderer_version",
            result.reason,
        )

    def test_samples_change_invalidates_baseline(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=64,
            mesh_mode="surface_nets",
            material_mode=(
                "projected-color-v1"
            ),
            samples=8,
            turntable_views=8,
            render_size=384,
        )

        result = self.check(
            config=config
        )

        self.assertFalse(
            result.compatible
        )

        self.assertIn(
            "configuration-mismatch:samples",
            result.reason,
        )

    def test_render_size_change_invalidates_baseline(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=64,
            mesh_mode="surface_nets",
            material_mode=(
                "projected-color-v1"
            ),
            samples=1,
            turntable_views=8,
            render_size=512,
        )

        result = self.check(
            config=config
        )

        self.assertFalse(
            result.compatible
        )

        self.assertIn(
            "configuration-mismatch:render_size",
            result.reason,
        )

    def test_turntable_view_count_invalidates_baseline(
        self,
    ) -> None:
        config = BaselineConfig(
            resolution=64,
            mesh_mode="surface_nets",
            material_mode=(
                "projected-color-v1"
            ),
            samples=1,
            turntable_views=12,
            render_size=384,
        )

        result = self.check(
            config=config
        )

        self.assertFalse(
            result.compatible
        )

        self.assertIn(
            "configuration-mismatch:turntable_views",
            result.reason,
        )

    def test_source_change_invalidates_baseline(
        self,
    ) -> None:
        self.repository.sheet1.write_bytes(
            b"sheet-one-modified"
        )

        result = self.check()

        self.assertFalse(
            result.compatible
        )

        self.assertEqual(
            result.reason,
            "source-hash-mismatch",
        )

    def test_missing_source_invalidates_baseline(
        self,
    ) -> None:
        missing = (
            self.repository.root
            / "missing.png"
        )

        result = self.check(
            source=missing
        )

        self.assertFalse(
            result.compatible
        )

        self.assertTrue(
            result.reason.startswith(
                "source-sheet-missing:"
            )
        )

    def test_missing_profile_invalidates_baseline(
        self,
    ) -> None:
        result = self.check(
            profile="L42"
        )

        self.assertFalse(
            result.compatible
        )

        self.assertEqual(
            result.reason,
            "profile-missing:L42",
        )

    def test_missing_sheet_invalidates_baseline(
        self,
    ) -> None:
        result = self.check(
            sheet="sheet42"
        )

        self.assertFalse(
            result.compatible
        )

        self.assertEqual(
            result.reason,
            "sheet-missing:sheet42",
        )

    def test_missing_configuration_invalidates_baseline(
        self,
    ) -> None:
        manifest = dict(
            self.manifest
        )

        manifest.pop(
            "configuration"
        )

        result = self.check(
            manifest=manifest
        )

        self.assertFalse(
            result.compatible
        )

        self.assertEqual(
            result.reason,
            "missing-configuration",
        )

    def test_output_layout_change_invalidates_baseline(
        self,
    ) -> None:
        manifest = json.loads(
            json.dumps(
                self.manifest
            )
        )

        manifest[
            "outputs"
        ][
            "material"
        ] = (
            "different.png"
        )

        result = self.check(
            manifest=manifest
        )

        self.assertFalse(
            result.compatible
        )

        self.assertEqual(
            result.reason,
            (
                "output-layout-mismatch:"
                "material"
            ),
        )


# ---------------------------------------------------------
# CLI tests
# ---------------------------------------------------------
