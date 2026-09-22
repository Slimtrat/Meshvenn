"""CLI and compatibility facade for batch native example generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.projected_material import BLEND_MODE, MATERIAL_MODE, VISIBILITY_MODE
from scripts.generate_example_native import process_sheet
from scripts.generate_all_native_support.discovery import (
    _validate_example_dir,
    discover_examples,
    discover_sheets,
    filter_from_sheet,
)
from scripts.generate_all_native_support.options import (
    normalize_profiles,
    parse_args,
    validate_numeric_args,
)
from scripts.generate_all_native_support.runner import main, print_plan
from scripts.run_logger import RunLogger


if __name__ == "__main__":
    main()