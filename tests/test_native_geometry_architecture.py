from __future__ import annotations

import ast
import ctypes
import unittest
from pathlib import Path

import core.geometry_contracts as geometry_contracts
import core.native_bridge as native_bridge

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PACKAGES = (
    ROOT / "core" / "geometry_contracts",
    ROOT / "core" / "native_bridge",
    ROOT / "implementations" / "native_visual_hull",
)


class NativeGeometryArchitectureTests(unittest.TestCase):
    def test_public_geometry_contract_facade_is_stable(self) -> None:
        self.assertEqual(
            set(geometry_contracts.__all__),
            {
                "DEFAULT_PROJECTION_CONVENTION",
                "GeometryProjectionConvention",
                "GeometryProjectionSpace",
                "GeometrySurfaceOutput",
                "require_geometry_surface_output",
                "validate_geometry_surface_output",
            },
        )

    def test_native_abi_structures_remain_ctypes_structures(self) -> None:
        expected_fields = {
            native_bridge.BptProjectionInput: (
                "mask",
                "width",
                "height",
                "azimuth_degrees",
                "elevation_degrees",
                "flip_x",
                "reserved_0",
                "reserved_1",
                "reserved_2",
            ),
            native_bridge.BptScanOptions: (
                "resolution",
                "symmetry_x",
                "reserved_0",
                "reserved_1",
                "reserved_2",
                "thread_count",
            ),
            native_bridge.BptVolumeResult: (
                "width",
                "depth",
                "height",
                "values",
                "value_count",
                "occupied_count",
                "has_bounds",
                "reserved_0",
                "reserved_1",
                "reserved_2",
                "min_x",
                "max_x",
                "min_y",
                "max_y",
                "min_z",
                "max_z",
            ),
            native_bridge.BptMeshOptions: (
                "voxel_size",
                "mode",
                "center_xy",
                "reserved_0",
                "reserved_1",
                "reserved_2",
            ),
            native_bridge.BptMeshResult: (
                "vertices",
                "vertex_float_count",
                "indices",
                "index_count",
                "polygon_starts",
                "polygon_sizes",
                "polygon_count",
            ),
        }
        for structure, field_names in expected_fields.items():
            with self.subTest(structure=structure.__name__):
                self.assertTrue(issubclass(structure, ctypes.Structure))
                self.assertEqual(
                    tuple(name for name, *_ in structure._fields_),
                    field_names,
                )

    def test_core_packages_do_not_import_blender(self) -> None:
        for package in PRODUCTION_PACKAGES[:2]:
            for path in package.glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                imported_roots = {
                    alias.name.split(".", 1)[0]
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                self.assertNotIn("bpy", imported_roots, path)

    def test_production_modules_stay_below_500_lines(self) -> None:
        for package in PRODUCTION_PACKAGES:
            for path in package.glob("*.py"):
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertLess(
                        len(path.read_text(encoding="utf-8-sig").splitlines()), 500
                    )

    def test_visual_hull_execute_method_is_a_thin_delegate(self) -> None:
        path = ROOT / "implementations" / "native_visual_hull" / "implementation.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        implementation = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "NativeVisualHullImplementation"
        )
        execute = next(
            node
            for node in implementation.body
            if isinstance(node, ast.FunctionDef) and node.name == "execute"
        )
        self.assertLessEqual(len(execute.body), 1)


if __name__ == "__main__":
    unittest.main()
