from __future__ import annotations

import ast
import unittest
from pathlib import Path

import core.uv_bake as uv_bake


ROOT = Path(__file__).resolve().parents[1]


class UVBakeArchitectureTests(unittest.TestCase):
    def test_core_public_api_remains_available(self) -> None:
        expected = {
            "SurfaceColorSample", "SurfaceColorSampler", "TextureBuffer",
            "UVBakeConfig", "UVBakeProgress", "UVBakeProgressCallback",
            "UVBakeResult", "UVBakeStats", "UVBakeTriangle", "UVBakeVertex",
            "bake_uv_texture", "square_texture_config", "texture_memory_bytes",
        }
        self.assertTrue(expected.issubset(set(uv_bake.__all__)))
        for name in expected:
            self.assertTrue(hasattr(uv_bake, name), name)

    def test_core_does_not_import_blender(self) -> None:
        for path in (ROOT / "core" / "uv_bake").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            imports = {
                alias.name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            self.assertNotIn("bpy", imports, str(path))

    def test_production_modules_stay_below_500_lines(self) -> None:
        roots = (ROOT / "core" / "uv_bake", ROOT / "implementations" / "uv_bake")
        for package in roots:
            for path in package.glob("*.py"):
                count = len(path.read_text(encoding="utf-8-sig").splitlines())
                self.assertLess(count, 500, f"{path} has {count} lines")


if __name__ == "__main__":
    unittest.main()
