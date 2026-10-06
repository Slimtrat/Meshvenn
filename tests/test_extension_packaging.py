"""Keep the extension's explicit CI copy list complete before native builds run."""

from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"


def core_package_sources(workflow):
    """Read the real Build package directory core copy arguments, not a test list."""
    step = workflow.split("- name: Build package directory", 1)[1].split("- name:", 1)[0]
    patterns = re.findall(r"(?m)^\s+(core/[^\s]+)\s+\\$", step)
    if not patterns:
        raise ValueError("Extension build has no recognized core copy inputs.")
    paths = set()
    for pattern in patterns:
        for source in ROOT.glob(pattern):
            paths.update(source.rglob("*.py") if source.is_dir() else (source,))
    return paths


class ExtensionPackagingTests(unittest.TestCase):
    def test_every_core_module_is_in_the_actual_build_copy_list(self):
        expected = set((ROOT / "core").rglob("*.py"))
        actual = core_package_sources(WORKFLOW.read_text("utf-8"))
        self.assertEqual(actual, expected, "The CI core copy list omits a runtime package.")

    def test_missing_modular_package_is_detected_before_build(self):
        workflow = WORKFLOW.read_text("utf-8")
        broken = re.sub(r"(?m)^\s+core/modular_character\s+\\\n", "", workflow)
        missing = set((ROOT / "core").rglob("*.py")) - core_package_sources(broken)
        self.assertEqual(missing, set((ROOT / "core/modular_character").glob("*.py")))
        self.assertEqual(len(missing), 8)

    def test_zip_preserves_all_selected_core_modules_byte_for_byte(self):
        sources = core_package_sources(WORKFLOW.read_text("utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "extension-core.zip"
            with ZipFile(path, "w") as archive:
                for source in sorted(sources):
                    archive.write(source, "blender_projection_tool/" + source.relative_to(ROOT).as_posix())
            with ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), {
                    "blender_projection_tool/" + source.relative_to(ROOT).as_posix() for source in sources})
                for source in sources:
                    name = "blender_projection_tool/" + source.relative_to(ROOT).as_posix()
                    self.assertEqual(archive.read(name), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
