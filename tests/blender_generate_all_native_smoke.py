"""Run with Blender --background --python tests/blender_generate_all_native_smoke.py."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_all_native_support import runner


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="meshvenn-native-batch-") as root:
        examples_root = Path(root)
        sheets_dir = examples_root / "sample" / "sheets"
        sheets_dir.mkdir(parents=True)
        sheet = sheets_dir / "sheet1.png"
        sheet.touch()

        calls = []

        def fake_process_sheet(sheet_path, generated_root, args, *, logger):
            calls.append((sheet_path, generated_root, args.resolution, args.profiles))

        original_process_sheet = runner.process_sheet
        original_argv = sys.argv
        try:
            runner.process_sheet = fake_process_sheet
            sys.argv = [
                "blender",
                "--",
                "--examples",
                str(examples_root),
                "--example",
                "sample",
                "--profiles",
                "L2",
                "--resolution",
                "8",
            ]
            runner.main()
        finally:
            runner.process_sheet = original_process_sheet
            sys.argv = original_argv

        assert calls == [
            (sheet, examples_root / "sample" / "generated", 8, ["L2"])
        ]

    print("generate all native smoke OK")


if __name__ == "__main__":
    main()
