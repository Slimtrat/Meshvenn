from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import (
    DEFAULT_ALPHA_THRESHOLD,
    DEFAULT_ANGLE_LIMIT_DEGREES,
    DEFAULT_EXAMPLE_DIR,
    DEFAULT_ISLAND_MARGIN,
    DEFAULT_MESH_MODE,
    DEFAULT_PADDING_PIXELS,
    DEFAULT_PROFILES,
    DEFAULT_RESOLUTION,
    DEFAULT_SAMPLES_PER_AXIS,
    DEFAULT_SHEET_WHITE_THRESHOLD,
    DEFAULT_TARGET_HEIGHT,
    DEFAULT_TEXTURE_SIZE,
    DEFAULT_UV_LAYER_NAME,
    DEFAULT_VOXEL_SIZE,
    SUPPORTED_IMPLEMENTATIONS,
)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate identical Meshvenn geometry with "
            "multiple MATERIAL implementations for visual "
            "comparison."
        )
    )

    parser.add_argument(
        "--example-dir",
        type=Path,
        default=DEFAULT_EXAMPLE_DIR,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Comparison output directory. "
            "Defaults to <example-dir>/material-comparison."
        ),
    )

    parser.add_argument(
        "--sheets",
        nargs="*",
        default=None,
        help=(
            "Optional sheet names. "
            "Example: sheet1 sheet2. "
            "Default: every sheet*.png."
        ),
    )

    parser.add_argument(
        "--profiles",
        nargs="+",
        default=list(
            DEFAULT_PROFILES
        ),
        help=(
            "Native scan profiles. "
            "Example: L2 L4 L8 L10."
        ),
    )

    parser.add_argument(
        "--implementations",
        nargs="+",
        choices=(
            SUPPORTED_IMPLEMENTATIONS
        ),
        default=list(
            SUPPORTED_IMPLEMENTATIONS
        ),
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=DEFAULT_RESOLUTION,
    )

    parser.add_argument(
        "--mesh-mode",
        choices=(
            "surface_nets",
            "blocks",
        ),
        default=DEFAULT_MESH_MODE,
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=(
            DEFAULT_ALPHA_THRESHOLD
        ),
    )

    parser.add_argument(
        "--sheet-white-threshold",
        type=float,
        default=(
            DEFAULT_SHEET_WHITE_THRESHOLD
        ),
    )

    parser.add_argument(
        "--thread-count",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--symmetry-x",
        action="store_true",
    )

    parser.add_argument(
        "--voxel-size",
        type=float,
        default=DEFAULT_VOXEL_SIZE,
    )

    parser.add_argument(
        "--target-height",
        type=float,
        default=DEFAULT_TARGET_HEIGHT,
    )

    # -----------------------------------------------------
    # UV Bake preview configuration
    #
    # 256 is intentionally much cheaper than the product
    # default of 1024. The comparison is diagnostic first.
    # -----------------------------------------------------

    parser.add_argument(
        "--texture-size",
        type=int,
        choices=(
            64,
            128,
            256,
            512,
            1024,
            2048,
            4096,
        ),
        default=DEFAULT_TEXTURE_SIZE,
    )

    parser.add_argument(
        "--padding",
        type=int,
        default=DEFAULT_PADDING_PIXELS,
    )

    parser.add_argument(
        "--samples-per-axis",
        type=int,
        choices=(
            1,
            2,
            3,
            4,
        ),
        default=(
            DEFAULT_SAMPLES_PER_AXIS
        ),
    )

    parser.add_argument(
        "--uv-layer-name",
        default=DEFAULT_UV_LAYER_NAME,
    )

    parser.add_argument(
        "--island-margin",
        type=float,
        default=DEFAULT_ISLAND_MARGIN,
    )

    parser.add_argument(
        "--angle-limit",
        type=float,
        default=(
            DEFAULT_ANGLE_LIMIT_DEGREES
        ),
    )

    parser.add_argument(
        "--save-blend",
        action="store_true",
        help=(
            "Also save one .blend file per "
            "implementation/profile."
        ),
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    parser.add_argument(
        "--json-log",
        action="store_true",
    )

    return parser.parse_args(
        _script_arguments()
    )


# =========================================================
# Validation
# =========================================================

def validate_args(
    args: argparse.Namespace,
) -> None:
    if not (
        8
        <= args.resolution
        <= 256
    ):
        raise ValueError(
            (
                "Resolution must be "
                "between 8 and 256."
            )
        )

    if not (
        0.0
        <= args.threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Alpha threshold must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        <= args.sheet_white_threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Sheet white threshold must "
                "be inside [0, 1]."
            )
        )

    if args.thread_count < 0:
        raise ValueError(
            "Thread count cannot be negative."
        )

    if args.voxel_size <= 0.0:
        raise ValueError(
            "Voxel size must be positive."
        )

    if args.target_height <= 0.0:
        raise ValueError(
            "Target height must be positive."
        )

    if not (
        0
        <= args.padding
        <= 128
    ):
        raise ValueError(
            (
                "UV padding must be "
                "between 0 and 128."
            )
        )

    if not (
        0.0
        <= args.island_margin
        <= 1.0
    ):
        raise ValueError(
            (
                "UV island margin must "
                "be inside [0, 1]."
            )
        )

    if not (
        0.0
        < args.angle_limit
        <= 90.0
    ):
        raise ValueError(
            (
                "Smart UV angle limit must "
                "be inside ]0, 90]."
            )
        )

    if (
        not args.uv_layer_name
        or not args.uv_layer_name.strip()
    ):
        raise ValueError(
            "UV layer name cannot be empty."
        )

    normalized_profiles = []

    for profile in args.profiles:
        normalized = (
            str(profile)
            .strip()
            .upper()
        )

        if not normalized:
            continue

        if normalized not in {
            "L2",
            "L4",
            "L8",
            "L10",
        }:
            raise ValueError(
                (
                    "Unsupported profile: "
                    f"{normalized}"
                )
            )

        if normalized not in normalized_profiles:
            normalized_profiles.append(
                normalized
            )

    if not normalized_profiles:
        raise ValueError(
            "At least one profile is required."
        )

    args.profiles = (
        normalized_profiles
    )
