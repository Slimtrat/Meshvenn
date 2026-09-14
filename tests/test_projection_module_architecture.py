from __future__ import annotations

import ast
import importlib
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectionMathFacadeTests(unittest.TestCase):
    def test_public_facade_exports_stable_api(self) -> None:
        module = importlib.import_module("core.projection_math")
        expected = {
            "EPSILON",
            "NormalizedPoint",
            "ProjectedPoint",
            "ProjectionTransform",
            "grid_to_normalized",
            "surface_position_to_normalized",
            "compile_projection",
            "project_normalized_point",
            "project_surface_position",
            "direction_to_camera",
            "clamp01",
            "dot3",
            "normalize3",
        }
        self.assertEqual(set(module.__all__), expected)
        self.assertTrue(all(hasattr(module, name) for name in expected))

    def test_native_grid_and_surface_envelope_use_distinct_mappings(self) -> None:
        from core.projection_math import grid_to_normalized, surface_position_to_normalized

        self.assertEqual(grid_to_normalized(0, 5), -1.0)
        self.assertEqual(grid_to_normalized(4, 5), 1.0)
        self.assertEqual(grid_to_normalized(20, 1), 0.0)
        point = surface_position_to_normalized(
            (-2.0, -3.0, 0.0), width=4, depth=6, height=8
        )
        self.assertEqual((point.x, point.y, point.z), (-1.0, -1.0, -1.0))

    def test_projection_and_camera_conventions_remain_stable(self) -> None:
        from core.projection_math import (
            NormalizedPoint,
            compile_projection,
            direction_to_camera,
            project_normalized_point,
        )

        transform = compile_projection(
            azimuth_degrees=0.0, elevation_degrees=0.0, flip_x=False
        )
        projected = project_normalized_point(NormalizedPoint(1.0, 0.0, 1.0), transform)
        self.assertEqual((projected.u, projected.v), (1.0, 1.0))
        flipped = project_normalized_point(
            NormalizedPoint(1.0, 0.0, 1.0),
            compile_projection(
                azimuth_degrees=0.0, elevation_degrees=0.0, flip_x=True
            ),
        )
        self.assertEqual(flipped.u, 0.0)
        camera = direction_to_camera(azimuth_degrees=90.0, elevation_degrees=0.0)
        self.assertAlmostEqual(camera[0], 1.0)
        self.assertAlmostEqual(camera[1], 0.0)
        self.assertAlmostEqual(math.dist(camera, (0.0, 0.0, 0.0)), 1.0)


class ProjectionPackageArchitectureTests(unittest.TestCase):
    def test_refactored_modules_stay_below_size_limit(self) -> None:
        roots = (
            ROOT / "core" / "projection_math",
            ROOT / "implementations" / "projection_images",
        )
        modules = [path for root in roots for path in root.glob("*.py")]
        modules.extend(
            [
                ROOT / "implementations" / "__init__.py",
                ROOT / "implementations" / "catalog.py",
                ROOT / "implementations" / "registration.py",
            ]
        )
        oversized = {
            str(path.relative_to(ROOT)): len(path.read_text(encoding="utf-8").splitlines())
            for path in modules
            if len(path.read_text(encoding="utf-8").splitlines()) >= 500
        }
        self.assertEqual(oversized, {})

    def test_projection_math_core_does_not_import_blender(self) -> None:
        for path in (ROOT / "core" / "projection_math").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = {
                alias.name.split(".")[0]
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            self.assertNotIn("bpy", imports, str(path))

    def test_blender_dependency_is_confined_to_preparation(self) -> None:
        package = ROOT / "implementations" / "projection_images"
        importing_bpy = []
        for path in package.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(
                isinstance(node, (ast.Import, ast.ImportFrom))
                and any(alias.name == "bpy" for alias in node.names)
                for node in ast.walk(tree)
            ):
                importing_bpy.append(path.name)
        self.assertEqual(importing_bpy, ["preparation.py"])

    def test_catalog_order_and_defaults_are_source_stable(self) -> None:
        tree = ast.parse(
            (ROOT / "implementations" / "catalog.py").read_text(encoding="utf-8")
        )
        assignments = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                assignments[node.targets[0].id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                assignments[node.target.id] = node.value
        factories = assignments["BUILTIN_IMPLEMENTATION_FACTORIES"]
        self.assertIsInstance(factories, ast.Tuple)
        self.assertEqual(
            [element.id for element in factories.elts],
            [
                "ProjectionImagesImplementation",
                "NativeVisualHullImplementation",
                "SDFReconstructionImplementation",
                "ProjectedColorImplementation",
                "UVBakeImplementation",
            ],
        )
        source = ast.unparse(assignments["BUILTIN_DEFAULT_IMPLEMENTATION_IDS"])
        self.assertIn("'projection-images'", source)
        self.assertIn("'native-visual-hull'", source)
        self.assertIn("'projected-color-v1.2'", source)


if __name__ == "__main__":
    unittest.main()
