from __future__ import annotations

import argparse
import math
import shutil
import sys
from array import array
from pathlib import Path
import bpy
from mathutils import Vector

from core.presheet_layout import CELL_SPECS, pixel_bbox
from .source import CELL_INSET

def inset_bbox(
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    inset: int = CELL_INSET,
) -> tuple[
    int,
    int,
    int,
    int,
]:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    result = (
        x0 + inset,
        y0 + inset,
        x1 - inset,
        y1 - inset,
    )

    (
        ix0,
        iy0,
        ix1,
        iy1,
    ) = result

    if (
        ix1 <= ix0
        or iy1 <= iy0
    ):
        raise ValueError(
            (
                "Cell is too small after inset: "
                f"{bbox}"
            )
        )

    return result


def build_cells(
    sheet_width: int,
    sheet_height: int,
) -> list[
    tuple[
        str,
        float,
        float,
        tuple[
            int,
            int,
            int,
            int,
        ],
    ]
]:
    cells = []

    for (
        name,
        column,
        row,
        azimuth,
        elevation,
    ) in CELL_SPECS:
        bbox = pixel_bbox(
            sheet_width,
            sheet_height,
            column,
            row,
        )

        cells.append(
            (
                name,
                azimuth,
                elevation,
                inset_bbox(
                    bbox
                ),
            )
        )

    return cells


# ---------------------------------------------------------
# Cell cleanup
# ---------------------------------------------------------

def clear_cell(
    sheet_pixels: array,
    sheet_width: int,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
) -> None:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    for y in range(
        y0,
        y1,
    ):
        row_start = (
            (
                y
                * sheet_width
                + x0
            )
            * 4
        )

        for x in range(
            x0,
            x1,
        ):
            index = (
                row_start
                + (
                    x
                    - x0
                )
                * 4
            )

            sheet_pixels[
                index
            ] = 1.0

            sheet_pixels[
                index + 1
            ] = 1.0

            sheet_pixels[
                index + 2
            ] = 1.0

            sheet_pixels[
                index + 3
            ] = 1.0


# ---------------------------------------------------------
# Common framing
# ---------------------------------------------------------
