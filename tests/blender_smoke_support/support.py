from __future__ import annotations

import argparse
import importlib
import math
import sys
from pathlib import Path

import bpy

from .constants import *

# =========================================================
# CLI
# =========================================================

def _script_arguments() -> list[str]:
    if "--" not in sys.argv:
        return []

    index = sys.argv.index(
        "--"
    )

    return sys.argv[
        index + 1:
    ]


def _parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test the packaged "
            "Meshvenn Blender extension."
        )
    )

    parser.add_argument(
        "--package-root",
        default=str(
            DEFAULT_PACKAGE_ROOT
        ),
    )

    return parser.parse_args(
        _script_arguments()
    )


# =========================================================
# Helpers
# =========================================================

def _section(
    title: str,
) -> None:
    print()
    print("=" * 72)
    print(
        f"Meshvenn smoke | {title}"
    )
    print("=" * 72)


def _require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def _require_close(
    actual: float,
    expected: float,
    *,
    name: str,
    tolerance: float = 1e-6,
) -> None:
    if not math.isclose(
        float(actual),
        float(expected),
        rel_tol=tolerance,
        abs_tol=tolerance,
    ):
        raise AssertionError(
            (
                f"Unexpected {name}.\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )
        )


def _purge_package_modules(
    package_name: str,
) -> None:
    prefix = (
        package_name
        + "."
    )

    names = [
        name
        for name
        in tuple(
            sys.modules.keys()
        )
        if (
            name == package_name
            or name.startswith(
                prefix
            )
        )
    ]

    for name in sorted(
        names,
        key=len,
        reverse=True,
    ):
        sys.modules.pop(
            name,
            None,
        )


# =========================================================
# RNA helpers
# =========================================================

def _operator_rna_class(
    identifier: str,
):
    return (
        bpy.types.Operator
        .bl_rna_get_subclass_py(
            identifier
        )
    )


def _panel_rna_class(
    identifier: str,
):
    return (
        bpy.types.Panel
        .bl_rna_get_subclass_py(
            identifier
        )
    )


def _ui_list_rna_class(
    identifier: str,
):
    return (
        bpy.types.UIList
        .bl_rna_get_subclass_py(
            identifier
        )
    )


def _operator_callable(
    idname: str,
):
    namespace_name, operator_name = (
        idname.split(
            ".",
            1,
        )
    )

    return getattr(
        getattr(
            bpy.ops,
            namespace_name,
        ),
        operator_name,
    )


def _operator_available(
    idname: str,
) -> bool:
    try:
        _operator_callable(
            idname
        ).get_rna_type()

        return True

    except Exception:
        return False


# =========================================================
# Package tree
# =========================================================

def _validate_package_tree(
    package_root: Path,
) -> None:
    _section(
        "package tree"
    )

    _require(
        package_root.is_dir(),
        (
            "Package directory does not exist: "
            f"{package_root}"
        ),
    )

    missing = [
        relative_path
        for relative_path
        in REQUIRED_PACKAGE_FILES
        if not (
            package_root
            / relative_path
        ).is_file()
    ]

    if missing:
        formatted = "\n".join(
            f"  - {path}"
            for path
            in missing
        )

        raise AssertionError(
            (
                "Packaged Meshvenn extension "
                "is incomplete.\n"
                f"{formatted}"
            )
        )

    print(
        "Package tree: OK"
    )

    for relative_path in (
        REQUIRED_PACKAGE_FILES
    ):
        print(
            f"  OK  {relative_path}"
        )


# =========================================================
# Extension import
# =========================================================

def _load_extension(
    package_root: Path,
):
    _section(
        "import extension"
    )

    package_root = (
        package_root.resolve()
    )

    package_parent = (
        package_root.parent
    )

    package_name = (
        package_root.name
    )

    _purge_package_modules(
        package_name
    )

    parent_string = str(
        package_parent
    )

    if (
        parent_string
        not in sys.path
    ):
        sys.path.insert(
            0,
            parent_string,
        )

    module = importlib.import_module(
        package_name
    )

    _require(
        callable(
            getattr(
                module,
                "register",
                None,
            )
        ),
        (
            "Extension does not expose "
            "register()."
        ),
    )

    _require(
        callable(
            getattr(
                module,
                "unregister",
                None,
            )
        ),
        (
            "Extension does not expose "
            "unregister()."
        ),
    )

    print(
        f"Package root: {package_root}"
    )

    print(
        f"Module name: {package_name}"
    )

    print(
        "Import: OK"
    )

    return (
        module,
        package_name,
    )
