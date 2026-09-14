from __future__ import annotations

import ast
import importlib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PipelineArchitectureTests(unittest.TestCase):
    def test_public_facades_are_packages(self) -> None:
        for name in ("pipeline_contracts", "pipeline_registry", "pipeline_runner"):
            module = importlib.import_module(f"core.{name}")
            self.assertEqual(Path(module.__file__).name, "__init__.py")

    def test_pipeline_modules_stay_blender_independent(self) -> None:
        for package in ("pipeline_contracts", "pipeline_registry", "pipeline_runner"):
            for path in (REPO_ROOT / "core" / package).glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                imported = {
                    alias.name.split(".", 1)[0]
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                imported.update(
                    (node.module or "").split(".", 1)[0]
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                )
                self.assertNotIn("bpy", imported, str(path))

    def test_production_modules_remain_focused(self) -> None:
        for package in ("pipeline_contracts", "pipeline_registry", "pipeline_runner"):
            for path in (REPO_ROOT / "core" / package).glob("*.py"):
                lines = len(path.read_text(encoding="utf-8").splitlines())
                self.assertLess(lines, 500, str(path))


if __name__ == "__main__":
    unittest.main()
