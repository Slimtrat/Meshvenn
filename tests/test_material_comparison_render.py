from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.material_comparison_render.cli import parse_args, validate_args
from scripts.material_comparison_render.config import REPO_ROOT
from scripts.material_comparison_render.variants import (
    discover_sheets,
    load_variant,
    validate_geometry_parity,
)


class MaterialComparisonRenderTests(unittest.TestCase):
    def test_config_resolves_repository_after_module_split(self) -> None:
        self.assertEqual(REPO_ROOT, Path(__file__).resolve().parents[1])

    def test_cli_keeps_blender_arguments(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "blender",
                "--background",
                "--",
                "--profiles",
                "l2",
                "l2",
                "--views",
                "4",
            ],
        ):
            args = parse_args()

        validate_args(args)
        self.assertEqual(args.profiles, ["L2"])
        self.assertEqual(args.views, 4)

    def test_load_variant_and_geometry_parity(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            comparison_root = Path(root)
            variants = []
            for implementation in ("projected-color-v1.2", "uv-bake-v2"):
                variant_root = comparison_root / "sheet1" / "L2" / implementation
                variant_root.mkdir(parents=True)
                (variant_root / "model.glb").touch()
                (variant_root / "variant.json").write_text(
                    json.dumps(
                        {
                            "geometry": {
                                "vertices": 8,
                                "faces": 6,
                                "dimensions": [1.0, 1.0, 2.0],
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                variants.append(
                    load_variant(
                        comparison_root,
                        sheet="sheet1",
                        profile="L2",
                        implementation=implementation,
                    )
                )

            self.assertEqual(discover_sheets(comparison_root, None), ["sheet1"])
            validate_geometry_parity(variants)
            variants[1].metadata["geometry"]["vertices"] = 9
            with self.assertRaisesRegex(RuntimeError, "Geometry parity failure"):
                validate_geometry_parity(variants)


if __name__ == "__main__":
    unittest.main()
