from __future__ import annotations

from .shared import Path, argparse, sys

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
            "Generate Projection Tool "
            "examples using the native "
            "C++ engine."
        )
    )

    parser.add_argument(
        "example_dir",
        type=Path,
    )

    parser.add_argument(
        "output_dir",
        type=Path,
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
        "--profiles",
        nargs="*",
        default=None,
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
        "--json-log",
        action="store_true",
    )

    parser.add_argument(
        "--skip-blend",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )
