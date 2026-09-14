from __future__ import annotations

import math
import unittest

from array import array

from core.uv_bake import (
    DEFAULT_TEXTURE_SIZE,
    MAX_PADDING_PIXELS,
    MAX_SAMPLES_PER_AXIS,
    MAX_TEXTURE_DIMENSION,
    SurfaceColorSample,
    TextureBuffer,
    UVBakeConfig,
    UVBakeTriangle,
    UVBakeVertex,
    bake_uv_texture,
    square_texture_config,
    texture_memory_bytes,
)


# =========================================================
# Helpers
# =========================================================

def vertex(
    x: float,
    y: float,
    z: float,
    u: float,
    v: float,
    *,
    normal: tuple[
        float,
        float,
        float,
    ] = (
        0.0,
        0.0,
        1.0,
    ),
) -> UVBakeVertex:
    return UVBakeVertex(
        position=(
            x,
            y,
            z,
        ),
        normal=normal,
        uv=(
            u,
            v,
        ),
    )


def unit_triangle(
    *,
    z: float = 0.0,
    source_index: int = 0,
) -> UVBakeTriangle:
    """
    UV triangle:

        (0,1)
          |
          |\
          | \
          |  \
          |___\
        (0,0) (1,0)

    Position X/Y deliberately matches UV U/V.
    """

    return UVBakeTriangle(
        a=vertex(
            0.0,
            0.0,
            z,
            0.0,
            0.0,
        ),
        b=vertex(
            1.0,
            0.0,
            z,
            1.0,
            0.0,
        ),
        c=vertex(
            0.0,
            1.0,
            z,
            0.0,
            1.0,
        ),
        source_index=source_index,
    )


def reversed_unit_triangle() -> UVBakeTriangle:
    return UVBakeTriangle(
        a=vertex(
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ),
        b=vertex(
            0.0,
            1.0,
            0.0,
            0.0,
            1.0,
        ),
        c=vertex(
            1.0,
            0.0,
            0.0,
            1.0,
            0.0,
        ),
    )


def constant_sampler(
    color=(
        1.0,
        0.0,
        0.0,
        1.0,
    ),
):
    def sample(
        position,
        normal,
    ):
        return color

    return sample
