from __future__ import annotations

import argparse
import importlib
import math
import sys
from pathlib import Path

from .constants import *

# =========================================================
# CLI
# =========================================================

def _script_arguments(
) -> list[str]:
    if "--" not in sys.argv:
        return []

    separator_index = (
        sys.argv.index(
            "--"
        )
    )

    return sys.argv[
        separator_index + 1:
    ]


def _parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Functional Blender smoke test "
            "for Meshvenn UV Bake V2."
        )
    )

    parser.add_argument(
        "--package-root",
        default=str(
            DEFAULT_PACKAGE_ROOT
        ),
        help=(
            "Path to the unpacked Meshvenn "
            "Blender extension."
        ),
    )

    return parser.parse_args(
        _script_arguments()
    )


# =========================================================
# Generic helpers
# =========================================================

def _section(
    title: str,
) -> None:
    print()

    print(
        "=" * 72
    )

    print(
        f"Meshvenn UV Bake smoke | {title}"
    )

    print(
        "=" * 72
    )


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
    message: str,
    tolerance: float = FLOAT_TOLERANCE,
) -> None:
    if not math.isclose(
        float(actual),
        float(expected),
        rel_tol=tolerance,
        abs_tol=tolerance,
    ):
        raise AssertionError(
            (
                f"{message}\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )
        )


def _clamp01(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            1.0,
            float(value),
        ),
    )


def _quantize_unorm8(
    value: float,
) -> float:
    """
    Reproduce the expected storage precision of the Blender
    image created by UV Bake V2:

        float_buffer=False

    Example:

        0.0625
            ↓
        round(0.0625 * 255)
            ↓
        16
            ↓
        16 / 255
            ↓
        0.062745098...
    """

    normalized = (
        _clamp01(
            value
        )
    )

    integer = math.floor(
        normalized
        * 255.0
        + 0.5
    )

    integer = max(
        0,
        min(
            255,
            integer,
        ),
    )

    return (
        float(integer)
        / 255.0
    )


def _require_rgba8_close(
    actual: float,
    source_float: float,
    *,
    message: str,
) -> None:
    expected = (
        _quantize_unorm8(
            source_float
        )
    )

    _require_close(
        actual,
        expected,
        message=message,
        tolerance=(
            RGBA8_TOLERANCE
        ),
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
