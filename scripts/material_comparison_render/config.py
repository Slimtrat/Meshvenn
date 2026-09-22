from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# =========================================================
# Defaults
# =========================================================

DEFAULT_COMPARISON_ROOT = (
    REPO_ROOT
    / "example"
    / "mascotte"
    / "test1"
    / "material-comparison"
)

DEFAULT_PROFILES = (
    "L2",
    "L4",
    "L8",
    "L10",
)

DEFAULT_IMPLEMENTATIONS = (
    "projected-color-v1.2",
    "uv-bake-v2",
)

DEFAULT_VIEWS = 8

DEFAULT_SIZE = 384

DEFAULT_SAMPLES = 1

DEFAULT_GUTTER = 8

BACKGROUND_COLOR = (
    0.025,
    0.025,
    0.03,
    1.0,
)

DIMENSION_TOLERANCE = 1e-5


# =========================================================
# Variant
# =========================================================

@dataclass(frozen=True)
class Variant:
    sheet: str

    profile: str

    implementation: str

    root: Path

    model_path: Path

    manifest_path: Path

    render_root: Path

    contact_sheet_path: Path

    metadata: dict[str, Any]
