from __future__ import annotations

import ast
import unittest
from pathlib import Path

import core.material_blend as material_blend
import core.material_visibility as material_visibility


ROOT = Path(__file__).resolve().parents[1]


class MaterialArchitectureTests(unittest.TestCase):
    def test_pure_core_public_apis_remain_available(self) -> None:
        expected = {
            material_blend: {
                "Color4", "MIN_SCORE", "MIN_WEIGHT", "MaterialBlendConfig",
                "MaterialColorCandidate", "ScoredMaterialCandidate",
                "MaterialBlendResult", "blend_candidates", "candidate_score",
                "choose_best_candidate", "clamp01", "facing_confidence",
                "smoothstep",
            },
            material_visibility: {
                "Vector3", "DEFAULT_RELATIVE_EPSILON",
                "DEFAULT_ABSOLUTE_EPSILON", "DEFAULT_RAY_LENGTH_MULTIPLIER",
                "MIN_DIRECTION_LENGTH", "MIN_RAY_DISTANCE", "RaycastHit",
                "RaycastFunction", "VisibilityConfig", "VisibilityResult",
                "MeshVisibilityTester", "bounding_box_diagonal",
                "compute_surface_epsilon", "compute_ray_distance",
            },
        }
        for module, names in expected.items():
            self.assertTrue(names <= set(module.__all__))
            for name in names:
                self.assertTrue(hasattr(module, name), name)

    def test_blender_facades_keep_expected_symbols(self) -> None:
        expected = {
            "core/projected_material/__init__.py": {
                "COLOR_ATTRIBUTE_NAME", "MATERIAL_NAME", "MATERIAL_MODE",
                "VISIBILITY_MODE", "BLEND_MODE", "DEFAULT_FALLBACK_COLOR",
                "MIN_ALPHA", "MIN_BASE_WEIGHT", "FALLBACK_FACING_FLOOR",
                "ImageBuffer", "ProjectedMaterialView",
                "MaterialProjectionStats", "ProjectedColorResult",
                "blend_projected_color", "ensure_projected_material",
                "apply_projected_material",
            },
            "implementations/projected_color/__init__.py": {
                "IMPLEMENTATION_ID", "DEFAULT_ENABLE_VISIBILITY",
                "DEFAULT_ALLOW_BACKFACE_FALLBACK", "DEFAULT_FACING_POWER",
                "DEFAULT_MIN_FACING", "DEFAULT_RELATIVE_SCORE_CUTOFF",
                "DEFAULT_MAX_CONTRIBUTORS", "DEFAULT_WEIGHT_POWER",
                "ProjectedColorConfig", "ProjectedColorOutput",
                "require_projected_color_output", "ProjectedColorImplementation",
            },
        }
        for relative, names in expected.items():
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8-sig"))
            visible = {
                alias.asname or alias.name
                for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            self.assertTrue(names <= visible, f"{relative}: missing {names - visible}")

    def test_blender_dependencies_stay_at_adapter_boundaries(self) -> None:
        allowed = {
            ROOT / "core/projected_material/image_buffer.py",
            ROOT / "core/projected_material/models.py",
            ROOT / "core/projected_material/blender_material.py",
            ROOT / "core/projected_material/application.py",
            ROOT / "implementations/projected_color/geometry.py",
            ROOT / "implementations/projected_color/metadata.py",
            ROOT / "implementations/projected_color/implementation.py",
        }
        roots = (
            ROOT / "core/material_blend",
            ROOT / "core/material_visibility",
            ROOT / "core/projected_material",
            ROOT / "implementations/projected_color",
        )
        for package in roots:
            for path in package.glob("*.py"):
                if path in allowed:
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                imports = {
                    alias.name.split(".")[0]
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names
                }
                self.assertNotIn("bpy", imports, str(path))

    def test_material_modules_stay_below_size_limits(self) -> None:
        production = (
            ROOT / "core/material_blend",
            ROOT / "core/material_visibility",
            ROOT / "core/projected_material",
            ROOT / "implementations/projected_color",
        )
        test_packages = (
            ROOT / "tests/test_material_blend",
            ROOT / "tests/test_material_visibility",
        )
        for package in production:
            for path in package.glob("*.py"):
                count = len(path.read_text(encoding="utf-8-sig").splitlines())
                self.assertLess(count, 500, f"{path} has {count} lines")
        for package in test_packages:
            for path in package.glob("*.py"):
                count = len(path.read_text(encoding="utf-8-sig").splitlines())
                self.assertLess(count, 500, f"{path} has {count} lines")


if __name__ == "__main__":
    unittest.main()
