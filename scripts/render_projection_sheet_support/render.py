from __future__ import annotations

import argparse
import math
import shutil
import sys
from array import array
from pathlib import Path
import bpy
from mathutils import Vector

from .camera import place_projection_camera

def render_view(
    *,
    camera: bpy.types.Object,
    target: Vector,
    model_size: Vector,
    name: str,
    azimuth: float,
    elevation: float,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    ortho_scale: float,
    output_dir: Path,
) -> Path:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    width = (
        x1
        - x0
    )

    height = (
        y1
        - y0
    )

    scene = (
        bpy.context.scene
    )

    scene.render.resolution_x = (
        width
    )

    scene.render.resolution_y = (
        height
    )

    scene.render.resolution_percentage = (
        100
    )

    place_projection_camera(
        camera,
        target=target,
        model_size=model_size,
        azimuth_degrees=azimuth,
        elevation_degrees=elevation,
        ortho_scale=ortho_scale,
    )

    output_path = (
        output_dir
        / f"{name}.png"
    )

    scene.render.filepath = str(
        output_path.resolve()
    )

    print(
        (
            "Rendering projection view "
            f"{name} "
            f"(azimuth={azimuth:.0f}, "
            f"elevation={elevation:.0f})"
        )
    )

    bpy.ops.render.render(
        write_still=True
    )

    if not output_path.exists():
        raise RuntimeError(
            (
                "Render did not produce: "
                f"{output_path}"
            )
        )

    return output_path


# ---------------------------------------------------------
# Composite
# ---------------------------------------------------------

def composite_view(
    sheet_pixels: array,
    sheet_width: int,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
    render_path: Path,
) -> None:
    (
        x0,
        y0,
        x1,
        y1,
    ) = bbox

    expected_width = (
        x1
        - x0
    )

    expected_height = (
        y1
        - y0
    )

    image = bpy.data.images.load(
        str(
            render_path.resolve()
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
            width != expected_width
            or height != expected_height
        ):
            raise ValueError(
                (
                    "Unexpected rendered cell size: "
                    f"{width}x{height}, "
                    "expected "
                    f"{expected_width}x"
                    f"{expected_height}"
                )
            )

        render_pixels = array(
            "f",
            [0.0],
        ) * (
            width
            * height
            * 4
        )

        image.pixels.foreach_get(
            render_pixels
        )

        premultiplied = (
            image.alpha_mode
            == "PREMUL"
        )

        for local_y in range(
            height
        ):
            for local_x in range(
                width
            ):
                source_index = (
                    (
                        local_y
                        * width
                        + local_x
                    )
                    * 4
                )

                destination_index = (
                    (
                        (
                            y0
                            + local_y
                        )
                        * sheet_width
                        + (
                            x0
                            + local_x
                        )
                    )
                    * 4
                )

                alpha = max(
                    0.0,
                    min(
                        1.0,
                        render_pixels[
                            source_index + 3
                        ],
                    ),
                )

                if premultiplied:
                    red = (
                        render_pixels[
                            source_index
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                    green = (
                        render_pixels[
                            source_index + 1
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                    blue = (
                        render_pixels[
                            source_index + 2
                        ]
                        + (
                            1.0
                            - alpha
                        )
                    )

                else:
                    red = (
                        render_pixels[
                            source_index
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                    green = (
                        render_pixels[
                            source_index + 1
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                    blue = (
                        render_pixels[
                            source_index + 2
                        ]
                        * alpha
                        + (
                            1.0
                            - alpha
                        )
                    )

                sheet_pixels[
                    destination_index
                ] = red

                sheet_pixels[
                    destination_index + 1
                ] = green

                sheet_pixels[
                    destination_index + 2
                ] = blue

                sheet_pixels[
                    destination_index + 3
                ] = 1.0

    finally:
        bpy.data.images.remove(
            image
        )


# ---------------------------------------------------------
# Save final sheet
# ---------------------------------------------------------

def save_sheet(
    pixels: array,
    width: int,
    height: int,
    output_path: Path,
) -> None:
    output_path = (
        output_path.resolve()
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = bpy.data.images.new(
        name="BPT_ProjectionSheet",
        width=width,
        height=height,
        alpha=True,
    )

    try:
        image.pixels.foreach_set(
            pixels
        )

        image.filepath_raw = str(
            output_path
        )

        image.file_format = (
            "PNG"
        )

        image.save()

    finally:
        bpy.data.images.remove(
            image
        )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
