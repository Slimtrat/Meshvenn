from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.generate_all_native_support.discovery import (
    discover_examples,
    discover_sheets,
    filter_from_sheet,
)
from scripts.generate_all_native_support.options import (
    REPO_ROOT,
    normalize_profiles,
    parse_args,
    validate_numeric_args,
)


class GenerateAllNativeTests(unittest.TestCase):
    def test_cli_keeps_blender_double_dash_arguments(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["blender", "--background", "--", "--resolution", "8", "--profiles", "L2"],
        ):
            args = parse_args()

        validate_numeric_args(args)
        self.assertEqual(args.resolution, 8)
        self.assertEqual(normalize_profiles(args.profiles), ["L2"])
        self.assertEqual(REPO_ROOT, Path(__file__).resolve().parents[1])

    def test_discovery_and_resume_filter(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            examples_root = Path(root)
            for name in ("a", "b"):
                sheets_dir = examples_root / name / "sheets"
                sheets_dir.mkdir(parents=True)
                (sheets_dir / "sheet1.png").touch()

            examples = discover_examples(examples_root, "all")
            self.assertEqual([path.name for path in examples], ["a", "b"])
            sheets = discover_sheets(examples)
            self.assertEqual(len(sheets), 2)
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                filter_from_sheet(
                    sheets,
                    examples_root=examples_root,
                    start_sheet="sheet1.png",
                )
            remaining = filter_from_sheet(
                sheets,
                examples_root=examples_root,
                start_sheet="b/sheets/sheet1.png",
            )
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0][0].name, "b")

    def test_requested_example_cannot_escape_root(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "inside the examples root"):
                discover_examples(Path(root), "../")


if __name__ == "__main__":
    unittest.main()
