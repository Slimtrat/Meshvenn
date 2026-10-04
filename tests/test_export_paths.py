from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.export_paths import protect_source_paths, resolve_export_path


class ExportPathTests(unittest.TestCase):
    def test_source_cannot_be_overwritten_even_when_overwrite_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.glb"
            source.write_bytes(b"original")
            for overwrite in (False, True):
                with self.subTest(overwrite=overwrite), self.assertRaisesRegex(ValueError, "source file"):
                    resolve_export_path(source, overwrite, sources=(source,))
            self.assertEqual(source.read_bytes(), b"original")

    def test_hard_link_source_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.glb"
            alias = Path(directory) / "alias.glb"
            source.write_bytes(b"original")
            os.link(source, alias)
            with self.assertRaisesRegex(ValueError, "source file"):
                resolve_export_path(alias, True, sources=(source,))

    def test_symlink_alias_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.glb"
            alias = Path(directory) / "alias.glb"
            source.write_bytes(b"original")
            try:
                alias.symlink_to(source)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                resolve_export_path(alias, True, sources=(source,))

    def test_publication_guard_rechecks_a_late_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.glb"
            output = Path(directory) / "output.glb"
            source.write_bytes(b"original")
            resolve_export_path(output, True, sources=(source,))
            os.link(source, output)
            with self.assertRaisesRegex(ValueError, "source file"):
                protect_source_paths(output, (source,))

    def test_separate_destination_and_existing_overwrite_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.glb"
            self.assertEqual(resolve_export_path(path, False), path)
            path.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                resolve_export_path(path, False)
            self.assertEqual(resolve_export_path(path, True), path)

    def test_invalid_options(self):
        for value, overwrite, error in ((None, False, TypeError), ("", False, ValueError),
                                        ("out.gltf", False, ValueError), ("out.glb", 1, TypeError)):
            with self.subTest(value=value), self.assertRaises(error):
                resolve_export_path(value, overwrite)
