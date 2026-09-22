"""Create or validate a persistent visual-preview baseline manifest.

The public functions remain here for callers importing scripts.preview_baseline;
implementation lives in preview_baseline_support.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Direct execution (python scripts/preview_baseline.py) needs the repository
# root on sys.path; package imports already have it.
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.preview_baseline_support.models import (
    SCHEMA_VERSION, DEFAULT_RENDERER_VERSION, DEFAULT_OUTPUTS,
    BaselineError, BaselineConfig, CompatibilityResult,
)
from scripts.preview_baseline_support.manifest import (
    sha256_file, _repo_relative_path, _unique_names,
    build_manifest, write_manifest, load_manifest,
)
from scripts.preview_baseline_support.compatibility import check_compatibility
from scripts.preview_baseline_support.cli import (
    _add_config_arguments, _config_from_args, parse_args,
    _command_write, _command_check, main,
)

if __name__ == "__main__":
    raise SystemExit(main())
