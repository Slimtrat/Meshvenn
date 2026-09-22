from __future__ import annotations

from .support import *

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
