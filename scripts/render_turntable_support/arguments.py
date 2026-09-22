from __future__ import annotations

import argparse
import math
import shutil
import sys

from array import array
from pathlib import Path

import bpy
from mathutils import Vector


# =========================================================
# CLI
# =========================================================

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
            "Render lightweight static visual previews "
            "for a generated GLB."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--views",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--size",
        type=int,
        default=256,
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--keep-stills",
        action="store_true",
    )

    parser.add_argument(
        "--preserve-material",
        action="store_true",
        help=(
            "Keep materials imported from the GLB instead "
            "of replacing them with the neutral preview "
            "material. Required for material comparisons."
        ),
    )

    return parser.parse_args(
        argv
    )


# =========================================================
# Cleanup
# =========================================================
