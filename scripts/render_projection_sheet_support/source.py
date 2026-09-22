from __future__ import annotations

import argparse
import math
import shutil
import sys

from array import array
from pathlib import Path

import bpy

from mathutils import Vector


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


from core.presheet_layout import (
    CELL_SPECS,
    pixel_bbox,
)

from scripts.render_turntable import (
    center_objects,
    clear_scene,
    create_camera,
    ensure_preview_material,
    import_glb,
    look_at,
    setup_lighting,
    setup_render,
)


CELL_INSET = 2


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
            "Render a generated GLB back into "
            "the original Projection Tool sheet."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Generated GLB.",
    )

    parser.add_argument(
        "--template",
        required=True,
        type=Path,
        help=(
            "Original Projection Tool sheet "
            "used as the visual template."
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Generated Projection Tool PNG.",
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--framing",
        type=float,
        default=1.15,
        help=(
            "Common orthographic framing "
            "multiplier for every view."
        ),
    )

    parser.add_argument(
        "--material-mode",
        choices=(
            "neutral",
            "original",
        ),
        default="neutral",
        help=(
            "neutral = geometry preview; "
            "original = preserve GLB materials."
        ),
    )

    parser.add_argument(
        "--keep-stills",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )


# ---------------------------------------------------------
# Sheet image
# ---------------------------------------------------------

def load_sheet(
    path: Path,
) -> tuple[
    array,
    int,
    int,
]:
    path = path.resolve()

    if not path.exists():
        raise FileNotFoundError(
            (
                "Missing Projection Tool sheet: "
                f"{path}"
            )
        )

    image = bpy.data.images.load(
        str(
            path
        ),
        check_existing=False,
    )

    try:
        image.update()

        width = int(
            image.size[0]
        )

        height = int(
            image.size[1]
        )

        if (
            width <= 0
            or height <= 0
        ):
            raise ValueError(
                (
                    "Invalid Projection Tool "
                    f"sheet size: {width}x{height}"
                )
            )

        pixels = array(
            "f",
            [0.0],
        ) * (
            width
            * height
            * 4
        )

        image.pixels.foreach_get(
            pixels
        )

        return (
            pixels,
            width,
            height,
        )

    finally:
        bpy.data.images.remove(
            image
        )


# ---------------------------------------------------------
# Cell geometry
# ---------------------------------------------------------
