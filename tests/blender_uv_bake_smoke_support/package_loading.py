from __future__ import annotations

import importlib
import math
from pathlib import Path
from typing import Any

import bpy

from .constants import *
from .support import (_clamp01, _purge_package_modules, _quantize_unorm8, _require, _require_close, _require_rgba8_close, _section)

# =========================================================
# Package
# =========================================================

def _validate_package_tree(
    package_root: Path,
) -> None:
    _section(
        "package"
    )

    _require(
        package_root.is_dir(),
        (
            "Package root does not exist: "
            f"{package_root}"
        ),
    )

    for relative_path in (
        REQUIRED_PACKAGE_FILES
    ):
        path = (
            package_root
            / relative_path
        )

        _require(
            path.is_file(),
            (
                "Required packaged file "
                f"is missing: {relative_path}"
            ),
        )

        print(
            f"  OK  {relative_path}"
        )


def _import_package(
    package_root: Path,
):
    package_root = (
        package_root.resolve()
    )

    package_name = (
        package_root.name
    )

    package_parent = (
        package_root.parent
    )

    _purge_package_modules(
        package_name
    )

    package_parent_string = str(
        package_parent
    )

    if (
        package_parent_string
        not in sys.path
    ):
        sys.path.insert(
            0,
            package_parent_string,
        )

    package = (
        importlib.import_module(
            package_name
        )
    )

    print(
        f"Package import: {package_name}"
    )

    return (
        package,
        package_name,
    )
