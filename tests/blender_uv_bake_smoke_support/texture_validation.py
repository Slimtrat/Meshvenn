from __future__ import annotations

import importlib
import math
from pathlib import Path
from typing import Any

import bpy

from .constants import *
from .support import (_clamp01, _purge_package_modules, _quantize_unorm8, _require, _require_close, _require_rgba8_close, _section)

# =========================================================
# TextureBuffer
# =========================================================

def _expected_coordinate(
    pixel: int,
) -> float:
    return (
        (
            float(pixel)
            + 0.5
        )
        / float(
            TEXTURE_SIZE
        )
    )


def _expected_source_color(
    x: int,
    y: int,
) -> tuple[
    float,
    float,
    float,
    float,
]:
    return (
        _expected_coordinate(
            x
        ),
        _expected_coordinate(
            y
        ),
        0.25,
        1.0,
    )


def _validate_texture_buffer(
    result,
) -> None:
    _section(
        "TextureBuffer"
    )

    test_pixels = (
        (
            0,
            0,
        ),
        (
            3,
            2,
        ),
        (
            4,
            4,
        ),
        (
            7,
            7,
        ),
    )

    for (
        x,
        y,
    ) in test_pixels:
        actual = (
            result
            .texture
            .rgba(
                x,
                y,
            )
        )

        expected = (
            _expected_source_color(
                x,
                y,
            )
        )

        for channel in range(
            4
        ):
            _require_close(
                actual[
                    channel
                ],
                expected[
                    channel
                ],
                message=(
                    "TextureBuffer mismatch "
                    f"at ({x}, {y}), "
                    f"channel {channel}."
                ),
            )

        _require(
            result.is_covered(
                x,
                y,
            ),
            (
                "Expected texel is not "
                f"covered: ({x}, {y})."
            ),
        )

    print(
        "TextureBuffer colors: OK"
    )


# =========================================================
# Blender Image
# =========================================================

def _image_pixel_rgba(
    image: bpy.types.Image,
    x: int,
    y: int,
) -> tuple[
    float,
    float,
    float,
    float,
]:
    width = int(
        image.size[0]
    )

    offset = (
        (
            y
            * width
            + x
        )
        * 4
    )

    return (
        float(
            image.pixels[
                offset
            ]
        ),
        float(
            image.pixels[
                offset + 1
            ]
        ),
        float(
            image.pixels[
                offset + 2
            ]
        ),
        float(
            image.pixels[
                offset + 3
            ]
        ),
    )


def _validate_blender_image(
    implementation_module,
    obj,
    result,
):
    _section(
        "Blender image"
    )

    image = (
        implementation_module
        ._create_baked_image(
            obj,
            result,
        )
    )

    _require(
        int(
            image.size[0]
        )
        == TEXTURE_SIZE,
        (
            "Unexpected Blender image width."
        ),
    )

    _require(
        int(
            image.size[1]
        )
        == TEXTURE_SIZE,
        (
            "Unexpected Blender image height."
        ),
    )

    # -----------------------------------------------------
    # UV Bake V2 deliberately creates:
    #
    #     float_buffer=False
    #
    # The core TextureBuffer is FLOAT32, but the Blender
    # image stores each channel as normalized 8-bit.
    #
    # The smoke therefore verifies the expected UNORM8
    # representation rather than requiring impossible
    # float-exact equality.
    # -----------------------------------------------------

    test_pixels = (
        (
            0,
            0,
        ),
        (
            3,
            2,
        ),
        (
            4,
            4,
        ),
        (
            7,
            7,
        ),
    )

    for (
        x,
        y,
    ) in test_pixels:
        actual = (
            _image_pixel_rgba(
                image,
                x,
                y,
            )
        )

        source = (
            _expected_source_color(
                x,
                y,
            )
        )

        for channel in range(
            4
        ):
            _require_rgba8_close(
                actual[
                    channel
                ],
                source[
                    channel
                ],
                message=(
                    "Blender RGBA8 pixel "
                    "mismatch at "
                    f"({x}, {y}), "
                    f"channel {channel}."
                ),
            )

    # -----------------------------------------------------
    # Explicit regression for the CI failure that motivated
    # this test.
    #
    # Core:
    #
    #     0.0625
    #
    # Blender byte image:
    #
    #     16 / 255
    #     == 0.062745098...
    # -----------------------------------------------------

    bottom_left = (
        _image_pixel_rgba(
            image,
            0,
            0,
        )
    )

    expected_quantized = (
        _quantize_unorm8(
            0.0625
        )
    )

    _require_close(
        bottom_left[0],
        expected_quantized,
        message=(
            "Blender image did not "
            "store expected RGBA8 value."
        ),
        tolerance=(
            RGBA8_TOLERANCE
        ),
    )

    print(
        "Blender image: OK"
    )

    print(
        (
            "  name: "
            f"{image.name}"
        )
    )

    print(
        (
            "  size: "
            f"{image.size[0]}×"
            f"{image.size[1]}"
        )
    )

    print(
        (
            "  source R: "
            "0.062500000"
        )
    )

    print(
        (
            "  stored R: "
            f"{bottom_left[0]:.9f}"
        )
    )

    print(
        (
            "  RGBA8 R: "
            f"{expected_quantized:.9f}"
        )
    )

    return image
