from __future__ import annotations

from array import array
from pathlib import Path

import bpy

# =========================================================
# Image helpers
# =========================================================

def _load_image_pixels(
    path: Path,
) -> tuple[
    array,
    int,
    int,
]:
    image = (
        bpy.data.images.load(
            str(
                path.resolve()
            ),
            check_existing=False,
        )
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
            raise RuntimeError(
                (
                    "Invalid image size: "
                    f"{path}"
                )
            )

        pixels = (
            array(
                "f",
                [
                    0.0
                ],
            )
            * (
                width
                * height
                * 4
            )
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


def _image_size(
    path: Path,
) -> tuple[
    int,
    int,
]:
    image = (
        bpy.data.images.load(
            str(
                path.resolve()
            ),
            check_existing=False,
        )
    )

    try:
        image.update()

        return (
            int(
                image.size[0]
            ),
            int(
                image.size[1]
            ),
        )

    finally:
        bpy.data.images.remove(
            image
        )
