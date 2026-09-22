from __future__ import annotations

from .support import *

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
