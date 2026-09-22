from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest

from contextlib import (
    redirect_stderr,
    redirect_stdout,
)
from pathlib import Path


# ---------------------------------------------------------
# Repository import
# ---------------------------------------------------------

REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from scripts.preview_baseline import (
    DEFAULT_OUTPUTS,
    SCHEMA_VERSION,
    BaselineConfig,
    BaselineError,
    build_manifest,
    check_compatibility,
    load_manifest,
    main,
    sha256_file,
    write_manifest,
)


# ---------------------------------------------------------
# Fixtures
# ---------------------------------------------------------

DEFAULT_CONFIG = BaselineConfig(
    resolution=64,
    mesh_mode="surface_nets",
    material_mode="projected-color-v1",
    samples=1,
    turntable_views=8,
    render_size=384,
    renderer_version=1,
)


class TemporaryBaselineRepository:
    """
    Small isolated repository-like directory used by tests.

    Layout:

        root/
        └── example/
            └── mascotte/
                └── test1/
                    └── sheets/
                        ├── sheet1.png
                        └── sheet2.png
    """

    def __init__(
        self,
    ) -> None:
        self._temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self._temporary_directory.name
        )

        self.sheets_dir = (
            self.root
            / "example"
            / "mascotte"
            / "test1"
            / "sheets"
        )

        self.sheets_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.sheet1 = (
            self.sheets_dir
            / "sheet1.png"
        )

        self.sheet2 = (
            self.sheets_dir
            / "sheet2.png"
        )

        # These do not need to be valid PNGs.
        #
        # preview_baseline only hashes the source files.
        self.sheet1.write_bytes(
            b"sheet-one-source"
        )

        self.sheet2.write_bytes(
            b"sheet-two-source"
        )

    def close(
        self,
    ) -> None:
        self._temporary_directory.cleanup()

    def manifest(
        self,
        *,
        config: BaselineConfig = (
            DEFAULT_CONFIG
        ),
        profiles: list[str] | None = None,
        sheets: list[str] | None = None,
    ) -> dict:
        return build_manifest(
            repo_root=self.root,
            sheets_dir=self.sheets_dir,
            sheet_names=(
                sheets
                or [
                    "sheet1",
                    "sheet2",
                ]
            ),
            profiles=(
                profiles
                or [
                    "L2",
                    "L4",
                    "L8",
                    "L10",
                ]
            ),
            config=config,
            source_commit=(
                "0123456789abcdef"
            ),
        )


# ---------------------------------------------------------
# Config tests
# ---------------------------------------------------------
