from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest

from contextlib import (
    redirect_stderr,
    redirect_stdout,
)
from pathlib import Path


# ---------------------------------------------------------
# Repository import
# ---------------------------------------------------------

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from scripts.preview_baseline import (
    DEFAULT_OUTPUTS,
    SCHEMA_VERSION,
    BaselineConfig,
    BaselineError,
    build_manifest,
    check_compatibility,
    load_manifest,
    main,
    sha256_file,
    write_manifest,
)


# ---------------------------------------------------------
# Fixtures
# ---------------------------------------------------------

DEFAULT_CONFIG = BaselineConfig(
    resolution=64,
    mesh_mode="surface_nets",
    material_mode="projected-color-v1",
    samples=1,
    turntable_views=8,
    render_size=384,
    renderer_version=1,
)


class TemporaryBaselineRepository:
    """
    Small isolated repository-like directory used by tests.

    Layout:

        root/
        └── example/
            └── mascotte/
                └── test1/
                    └── sheets/
                        ├── sheet1.png
                        └── sheet2.png
    """

    def __init__(
        self,
    ) -> None:
        self._temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self._temporary_directory.name
        )

        self.sheets_dir = (
            self.root
            / "example"
            / "mascotte"
            / "test1"
            / "sheets"
        )

        self.sheets_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.sheet1 = (
            self.sheets_dir
            / "sheet1.png"
        )

        self.sheet2 = (
            self.sheets_dir
            / "sheet2.png"
        )

        # These do not need to be valid PNGs.
        #
        # preview_baseline only hashes the source files.
        self.sheet1.write_bytes(
            b"sheet-one-source"
        )

        self.sheet2.write_bytes(
            b"sheet-two-source"
        )

    def close(
        self,
    ) -> None:
        self._temporary_directory.cleanup()

    def manifest(
        self,
        *,
        config: BaselineConfig = (
            DEFAULT_CONFIG
        ),
        profiles: list[str] | None = None,
        sheets: list[str] | None = None,
    ) -> dict:
        return build_manifest(
            repo_root=self.root,
            sheets_dir=self.sheets_dir,
            sheet_names=(
                sheets
                or [
                    "sheet1",
                    "sheet2",
                ]
            ),
            profiles=(
                profiles
                or [
                    "L2",
                    "L4",
                    "L8",
                    "L10",
                ]
            ),
            config=config,
            source_commit=(
                "0123456789abcdef"
            ),
        )


# ---------------------------------------------------------
# Config tests
# ---------------------------------------------------------

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

class ManifestGenerationTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.repository = (
            TemporaryBaselineRepository()
        )

    def tearDown(
        self,
    ) -> None:
        self.repository.close()

    def test_manifest_contains_expected_metadata(
        self,
    ) -> None:
        manifest = (
            self.repository.manifest()
        )

        self.assertEqual(
            manifest[
                "schema_version"
            ],
            SCHEMA_VERSION,
        )

        self.assertEqual(
            manifest[
                "source_commit"
            ],
            "0123456789abcdef",
        )

        self.assertEqual(
            manifest[
                "configuration"
            ],
            DEFAULT_CONFIG.to_dict(),
        )

        self.assertEqual(
            manifest[
                "profiles"
            ],
            [
                "L2",
                "L4",
                "L8",
                "L10",
            ],
        )

        self.assertEqual(
            manifest[
                "outputs"
            ],
            DEFAULT_OUTPUTS,
        )

    def test_manifest_contains_source_hashes(
        self,
    ) -> None:
        manifest = (
            self.repository.manifest()
        )

        sheet = manifest[
            "sheets"
        ][
            "sheet1"
        ]

        self.assertEqual(
            sheet[
                "source"
            ],
            (
                "example/"
                "mascotte/"
                "test1/"
                "sheets/"
                "sheet1.png"
            ),
        )

        self.assertEqual(
            sheet[
                "source_sha256"
            ],
            sha256_file(
                self.repository.sheet1
            ),
        )

    def test_duplicates_are_removed(
        self,
    ) -> None:
        manifest = (
            self.repository.manifest(
                profiles=[
                    "L10",
                    "L10",
                    "L8",
                    "",
                    "L8",
                ],
                sheets=[
                    "sheet1",
                    "sheet1",
                    "sheet2",
                ],
            )
        )

        self.assertEqual(
            manifest[
                "profiles"
            ],
            [
                "L10",
                "L8",
            ],
        )

        self.assertEqual(
            list(
                manifest[
                    "sheets"
                ].keys()
            ),
            [
                "sheet1",
                "sheet2",
            ],
        )

    def test_missing_source_sheet_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            BaselineError
        ):
            self.repository.manifest(
                sheets=[
                    "sheet1",
                    "does-not-exist",
                ]
            )

    def test_empty_profiles_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            BaselineError
        ):
            build_manifest(
                repo_root=(
                    self.repository.root
                ),
                sheets_dir=(
                    self.repository.sheets_dir
                ),
                sheet_names=[
                    "sheet1"
                ],
                profiles=[
                    "",
                    " ",
                ],
                config=(
                    DEFAULT_CONFIG
                ),
                source_commit=(
                    "abc"
                ),
            )

    def test_empty_source_commit_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            BaselineError
        ):
            build_manifest(
                repo_root=(
                    self.repository.root
                ),
                sheets_dir=(
                    self.repository.sheets_dir
                ),
                sheet_names=[
                    "sheet1"
                ],
                profiles=[
                    "L10"
                ],
                config=(
                    DEFAULT_CONFIG
                ),
                source_commit="",
            )

    def test_source_must_be_inside_repository(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as external:
            external_root = Path(
                external
            )

            external_sheets = (
                external_root
                / "sheets"
            )

            external_sheets.mkdir()

            (
                external_sheets
                / "sheet1.png"
            ).write_bytes(
                b"external"
            )

            with self.assertRaises(
                BaselineError
            ):
                build_manifest(
                    repo_root=(
                        self.repository.root
                    ),
                    sheets_dir=(
                        external_sheets
                    ),
                    sheet_names=[
                        "sheet1"
                    ],
                    profiles=[
                        "L10"
                    ],
                    config=(
                        DEFAULT_CONFIG
                    ),
                    source_commit="abc",
                )


# ---------------------------------------------------------
# Manifest persistence tests
# ---------------------------------------------------------

class ManifestPersistenceTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.repository = (
            TemporaryBaselineRepository()
        )

    def tearDown(
        self,
    ) -> None:
        self.repository.close()

    def test_write_then_load_round_trip(
        self,
    ) -> None:
        manifest = (
            self.repository.manifest()
        )

        path = (
            self.repository.root
            / "docs"
            / "previews"
            / "manifest.json"
        )

        write_manifest(
            manifest,
            path,
        )

        loaded = load_manifest(
            path
        )

        self.assertEqual(
            loaded,
            manifest,
        )

    def test_manifest_output_is_deterministic(
        self,
    ) -> None:
        manifest = (
            self.repository.manifest()
        )

        first = (
            self.repository.root
            / "first.json"
        )

        second = (
            self.repository.root
            / "second.json"
        )

        write_manifest(
            manifest,
            first,
        )

        write_manifest(
            manifest,
            second,
        )

        self.assertEqual(
            first.read_bytes(),
            second.read_bytes(),
        )

    def test_invalid_json_rejected(
        self,
    ) -> None:
        path = (
            self.repository.root
            / "manifest.json"
        )

        path.write_text(
            "{ invalid json",
            encoding="utf-8",
        )

        with self.assertRaises(
            BaselineError
        ):
            load_manifest(
                path
            )

    def test_non_object_manifest_rejected(
        self,
    ) -> None:
        path = (
            self.repository.root
            / "manifest.json"
        )

        path.write_text(
            json.dumps(
                [
                    "not",
                    "an",
                    "object",
                ]
            ),
            encoding="utf-8",
        )

        with self.assertRaises(
            BaselineError
        ):
            load_manifest(
                path
            )


# ---------------------------------------------------------
# Compatibility tests
# ---------------------------------------------------------

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

class CliTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.repository = (
            TemporaryBaselineRepository()
        )

        self.manifest_path = (
            self.repository.root
            / "docs"
            / "previews"
            / "manifest.json"
        )

    def tearDown(
        self,
    ) -> None:
        self.repository.close()

    def _common_args(
        self,
    ) -> list[str]:
        return [
            "--resolution",
            "64",
            "--mesh-mode",
            "surface_nets",
            "--material-mode",
            "projected-color-v1",
            "--samples",
            "1",
            "--turntable-views",
            "8",
            "--render-size",
            "384",
            "--renderer-version",
            "1",
        ]

    def test_cli_write_creates_manifest(
        self,
    ) -> None:
        output = io.StringIO()

        args = [
            "write",
            "--repo-root",
            str(
                self.repository.root
            ),
            "--sheets-dir",
            str(
                self.repository.sheets_dir
            ),
            "--sheet-names",
            "sheet1",
            "sheet2",
            "--profiles",
            "L2",
            "L4",
            "L8",
            "L10",
            "--source-commit",
            "abcdef123456",
            "--output",
            str(
                self.manifest_path
            ),
            *self._common_args(),
        ]

        with redirect_stdout(
            output
        ):
            return_code = main(
                args
            )

        self.assertEqual(
            return_code,
            0,
        )

        self.assertTrue(
            self.manifest_path.is_file()
        )

        manifest = load_manifest(
            self.manifest_path
        )

        self.assertEqual(
            manifest[
                "source_commit"
            ],
            "abcdef123456",
        )

    def test_cli_check_accepts_matching_manifest(
        self,
    ) -> None:
        write_manifest(
            self.repository.manifest(),
            self.manifest_path,
        )

        output = io.StringIO()

        args = [
            "check",
            "--manifest",
            str(
                self.manifest_path
            ),
            "--sheet",
            "sheet1",
            "--source",
            str(
                self.repository.sheet1
            ),
            "--profile",
            "L10",
            *self._common_args(),
        ]

        with redirect_stdout(
            output
        ):
            return_code = main(
                args
            )

        self.assertEqual(
            return_code,
            0,
        )

        self.assertIn(
            (
                "compatible: "
                "sheet1/L10: "
                "compatible"
            ),
            output.getvalue(),
        )

    def test_cli_check_rejects_changed_source(
        self,
    ) -> None:
        write_manifest(
            self.repository.manifest(),
            self.manifest_path,
        )

        self.repository.sheet1.write_bytes(
            b"changed-after-manifest"
        )

        output = io.StringIO()

        args = [
            "check",
            "--manifest",
            str(
                self.manifest_path
            ),
            "--sheet",
            "sheet1",
            "--source",
            str(
                self.repository.sheet1
            ),
            "--profile",
            "L10",
            *self._common_args(),
        ]

        with redirect_stdout(
            output
        ):
            return_code = main(
                args
            )

        self.assertEqual(
            return_code,
            1,
        )

        self.assertIn(
            "source-hash-mismatch",
            output.getvalue(),
        )

    def test_cli_check_rejects_missing_manifest(
        self,
    ) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        args = [
            "check",
            "--manifest",
            str(
                self.manifest_path
            ),
            "--sheet",
            "sheet1",
            "--source",
            str(
                self.repository.sheet1
            ),
            "--profile",
            "L10",
            *self._common_args(),
        ]

        with (
            redirect_stdout(
                stdout
            ),
            redirect_stderr(
                stderr
            ),
        ):
            return_code = main(
                args
            )

        self.assertEqual(
            return_code,
            1,
        )

        self.assertIn(
            "incompatible:",
            stderr.getvalue(),
        )


# ---------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------

if __name__ == "__main__":
    unittest.main()