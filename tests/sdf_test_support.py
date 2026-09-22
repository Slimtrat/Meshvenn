from __future__ import annotations

import math
import unittest

from array import array
from types import SimpleNamespace

from core.image_mask import (
    BinaryMask,
)
from core.projection_math import (
    NormalizedPoint,
)
from core.sdf import (
    DEFAULT_ISO_LEVEL,
    DEFAULT_SMOOTHNESS,
    DEFAULT_SURFACE_OFFSET,
    DEFAULT_SYMMETRY_X,
    SDFBuildConfig,
    SDFProjection,
    SDFVolume,
    SignedDistanceMask,
    build_sdf_from_views,
    build_sdf_projections,
    build_sdf_volume,
    build_signed_distance_mask,
    cubic_sdf_config,
    fuse_signed_distances,
    sample_fused_sdf,
    smooth_max,
)


# =========================================================
# Mask helpers
# =========================================================

def mask_from_rows(
    *rows: str,
) -> BinaryMask:
    """
    Build a BinaryMask from ASCII rows.

        # = foreground
        . = background

    Rows are given bottom-to-top exactly as BinaryMask stores
    them. For symmetric synthetic masks this distinction does
    not affect the tests, but keeping the representation
    explicit avoids hidden image-coordinate assumptions.
    """

    if not rows:
        raise ValueError(
            "At least one row is required."
        )

    width = len(
        rows[0]
    )

    if width <= 0:
        raise ValueError(
            "Rows cannot be empty."
        )

    for row in rows:
        if len(
            row
        ) != width:
            raise ValueError(
                (
                    "All mask rows must have "
                    "the same width."
                )
            )

    values = bytearray()

    for row in rows:
        for value in row:
            if value == "#":
                values.append(
                    1
                )

            elif value == ".":
                values.append(
                    0
                )

            else:
                raise ValueError(
                    (
                        "Unsupported mask character: "
                        f"{value!r}"
                    )
                )

    return BinaryMask(
        width=width,
        height=len(
            rows
        ),
        values=bytes(
            values
        ),
    )


def centered_single_pixel_mask() -> BinaryMask:
    return mask_from_rows(
        ".....",
        ".....",
        "..#..",
        ".....",
        ".....",
    )


def centered_square_mask() -> BinaryMask:
    return mask_from_rows(
        ".......",
        ".......",
        "..###..",
        "..###..",
        "..###..",
        ".......",
        ".......",
    )


def centered_large_square_mask() -> BinaryMask:
    return mask_from_rows(
        ".........",
        ".........",
        "..#####..",
        "..#####..",
        "..#####..",
        "..#####..",
        "..#####..",
        ".........",
        ".........",
    )


def centered_circle_mask(
    *,
    size: int = 9,
    radius: float = 3.0,
) -> BinaryMask:
    center = (
        float(
            size - 1
        )
        * 0.5
    )

    values = bytearray()

    for y in range(
        size
    ):
        for x in range(
            size
        ):
            dx = (
                float(x)
                - center
            )

            dy = (
                float(y)
                - center
            )

            inside = (
                dx * dx
                + dy * dy
                <= radius * radius
            )

            values.append(
                1
                if inside
                else 0
            )

    return BinaryMask(
        width=size,
        height=size,
        values=bytes(
            values
        ),
    )

# Python has no `nine` constant; keeping construction
# explicit below avoids clever helpers becoming part of the
# test surface.
def circle_mask_9() -> BinaryMask:
    size = 9

    center = 4.0

    radius = 3.0

    values = bytearray()

    for y in range(
        size
    ):
        for x in range(
            size
        ):
            dx = (
                float(x)
                - center
            )

            dy = (
                float(y)
                - center
            )

            values.append(
                1
                if (
                    dx * dx
                    + dy * dy
                    <= radius * radius
                )
                else 0
            )

    return BinaryMask(
        width=size,
        height=size,
        values=bytes(
            values
        ),
    )


# =========================================================
# Signed-distance mask
# =========================================================
