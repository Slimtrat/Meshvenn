from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias

from .constants import *
from .texture import *

def _dilate_texture(
    texture: TextureBuffer,
    coverage: bytearray,
    *,
    padding_pixels: int,
) -> tuple[
    bytes,
    int,
]:
    """
    Expand baked colors around UV islands.

    The algorithm is a bounded multi-source breadth-first
    expansion.

    Every covered texel starts at distance 0.

    Neighbouring empty texels receive the nearest available
    baked color up to `padding_pixels` Manhattan distance.

    Coverage itself is NOT modified:

        coverage
            actual UV island

        filled
            UV island + padding
    """

    pixel_count = (
        texture.pixel_count
    )

    filled = bytearray(
        coverage
    )

    if (
        padding_pixels <= 0
        or pixel_count == 0
    ):
        return (
            bytes(
                filled
            ),
            0,
        )

    distances = (
        array(
            "H",
            [
                UNVISITED_DISTANCE
            ],
        )
        * pixel_count
    )

    queue = array(
        "I"
    )

    for pixel_index in range(
        pixel_count
    ):
        if not coverage[
            pixel_index
        ]:
            continue

        distances[
            pixel_index
        ] = 0

        queue.append(
            pixel_index
        )

    if not queue:
        return (
            bytes(
                filled
            ),
            0,
        )

    head = 0

    padded_pixels = 0

    width = (
        texture.width
    )

    height = (
        texture.height
    )

    last_row_start = (
        (
            height - 1
        )
        * width
    )

    while head < len(
        queue
    ):
        current = int(
            queue[
                head
            ]
        )

        head += 1

        current_distance = int(
            distances[
                current
            ]
        )

        if (
            current_distance
            >= padding_pixels
        ):
            continue

        next_distance = (
            current_distance
            + 1
        )

        x = (
            current
            % width
        )

        neighbours: list[
            int
        ] = []

        if x > 0:
            neighbours.append(
                current - 1
            )

        if x < (
            width - 1
        ):
            neighbours.append(
                current + 1
            )

        if current >= width:
            neighbours.append(
                current - width
            )

        if current < (
            last_row_start
        ):
            neighbours.append(
                current + width
            )

        for neighbour in (
            neighbours
        ):
            if (
                distances[
                    neighbour
                ]
                != UNVISITED_DISTANCE
            ):
                continue

            distances[
                neighbour
            ] = (
                next_distance
            )

            filled[
                neighbour
            ] = 1

            texture.copy_pixel(
                current,
                neighbour,
            )

            queue.append(
                neighbour
            )

            padded_pixels += 1

    return (
        bytes(
            filled
        ),
        padded_pixels,
    )


# =========================================================
# Public bake API
# =========================================================
