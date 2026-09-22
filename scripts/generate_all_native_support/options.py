from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def parse_args() -> argparse.Namespace:
    argv = sys.argv

    if "--" in argv:
        argv = argv[
            argv.index("--") + 1:
        ]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Generate Projection Tool examples "
            "with the native C++ engine inside "
            "one Blender process."
        )
    )

    parser.add_argument(
        "--examples",
        type=Path,
        default=(
            REPO_ROOT
            / "example"
        ),
    )

    parser.add_argument(
        "--example",
        default="all",
        help=(
            '"all" or an example path '
            'such as "mascotte/test1".'
        ),
    )

    parser.add_argument(
        "--start-sheet",
        default="",
        help=(
            "Optional sheet name/path "
            "to resume generation from."
        ),
    )

    parser.add_argument(
        "--profiles",
        nargs="*",
        default=None,
        help=(
            "Optional scan levels: "
            "L2 L4 L8 L10."
        ),
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=64,
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
    )

    parser.add_argument(
        "--sheet-white-threshold",
        type=float,
        default=0.94,
    )

    parser.add_argument(
        "--thread-count",
        type=int,
        default=0,
        help="0 = automatic CPU detection.",
    )

    parser.add_argument(
        "--symmetry-x",
        action="store_true",
    )

    parser.add_argument(
        "--voxel-size",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--target-height",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--mesh-mode",
        choices=(
            "blocks",
            "surface_nets",
        ),
        default="blocks",
        help=(
            "Mesh extraction algorithm. "
            "blocks preserves the historical "
            "voxel-face mesher; surface_nets "
            "uses smooth Surface Nets extraction."
        ),
    )

    parser.add_argument(
        "--skip-blend",
        action="store_true",
    )

    parser.add_argument(
        "--json-log",
        action="store_true",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )

# ---------------------------------------------------------
# Normalization / validation
# ---------------------------------------------------------

def normalize_profiles(
    profiles: list[str] | None,
) -> list[str] | None:
    if not profiles:
        return None

    return [
        profile
        .strip()
        .upper()
        for profile in profiles
        if profile.strip()
    ]


def validate_numeric_args(
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
                "Threshold must be "
                "between 0 and 1."
            )
        )

    if not (
        0.0
        <= args.sheet_white_threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Sheet white threshold must be "
                "between 0 and 1."
            )
        )

    if args.thread_count < 0:
        raise ValueError(
            (
                "Thread count cannot "
                "be negative."
            )
        )

    if args.voxel_size <= 0.0:
        raise ValueError(
            (
                "Voxel size must be "
                "greater than zero."
            )
        )

    if args.target_height <= 0.0:
        raise ValueError(
            (
                "Target height must be "
                "greater than zero."
            )
        )
