from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.material_comparison_generator.cli import parse_args, validate_args
from scripts.material_comparison_generator.config import REPO_ROOT
from scripts.material_comparison_generator.io import (
    discover_sheets,
    write_json,
)


class MaterialComparisonGeneratorTests(unittest.TestCase):
    def test_config_resolves_repository_after_module_split(self) -> None:
        self.assertEqual(REPO_ROOT, Path(__file__).resolve().parents[1])

    def test_cli_keeps_blender_double_dash_arguments(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["blender", "--background", "--", "--profiles", "l4", "L4"],
        ):
            args = parse_args()

        validate_args(args)
        self.assertEqual(args.profiles, ["L4"])
        self.assertEqual(
            args.implementations,
            ["projected-color-v1.2", "uv-bake-v2"],
        )

    def test_discovery_filters_requested_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            sheets = Path(root) / "sheets"
            sheets.mkdir()
            (sheets / "sheet2.png").touch()
            (sheets / "sheet1.png").touch()

            self.assertEqual(
                [path.name for path in discover_sheets(Path(root), ["sheet2"])],
                ["sheet2.png"],
            )

    def test_json_writer_preserves_manifest_shape(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "nested" / "comparison.json"
            write_json(output, {"paths": [Path(root)], "ok": True})
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                {"paths": [str(Path(root))], "ok": True},
            )


if __name__ == "__main__":
    unittest.main()
