from __future__ import annotations

import argparse
import math
import shutil
import sys
from array import array
from pathlib import Path
import bpy
from mathutils import Vector

from .camera import look_at

def view_angles(
    count: int,
) -> list[
    float
]:
    return [
        (
            2.0
            * math.pi
            * index
            / count
        )
        for index
        in range(
            count
        )
    ]


def place_camera(
    camera: bpy.types.Object,
    *,
    target: Vector,
    model_size: Vector,
    angle: float,
) -> None:
    framing_size = max(
        model_size.x,
        model_size.y,
        model_size.z,
        0.01,
    )

    distance = (
        framing_size
        * 3.0
    )

    height = (
        max(
            model_size.z,
            0.01,
        )
        * 0.05
    )

    camera.location = (
        math.sin(
            angle
        )
        * distance,

        -math.cos(
            angle
        )
        * distance,

        height,
    )

    look_at(
        camera,
        target,
    )


def render_views(
    *,
    camera: bpy.types.Object,
    target: Vector,
    model_size: Vector,
    output_dir: Path,
    views: int,
) -> list[
    Path
]:
    scene = (
        bpy.context.scene
    )

    stills_dir = (
        output_dir
        / "stills"
    )

    stills_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    outputs: list[
        Path
    ] = []

    angles = (
        view_angles(
            views
        )
    )

    for (
        index,
        angle,
    ) in enumerate(
        angles
    ):
        degrees = round(
            360.0
            * index
            / views
        )

        output_path = (
            stills_dir
            / f"view_{degrees:03d}.png"
        )

        place_camera(
            camera,
            target=target,
            model_size=model_size,
            angle=angle,
        )

        scene.render.filepath = str(
            output_path.resolve()
        )

        print(
            (
                "Rendering view "
                f"{degrees:03d}"
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

        outputs.append(
            output_path
        )

    return outputs


# =========================================================
# Contact sheet
# =========================================================

def build_contact_sheet(
    image_paths: list[
        Path
    ],
    output_path: Path,
) -> None:
    if not image_paths:
        raise RuntimeError(
            "No stills for contact sheet."
        )

    images: list[
        bpy.types.Image
    ] = []

    try:
        for path in (
            image_paths
        ):
            image = (
                bpy.data.images.load(
                    str(
                        path.resolve()
                    ),
                    check_existing=False,
                )
            )

            image.update()

            images.append(
                image
            )

        tile_width = int(
            images[0].size[0]
        )

        tile_height = int(
            images[0].size[1]
        )

        for image in images:
            if (
                int(
                    image.size[0]
                )
                != tile_width
                or int(
                    image.size[1]
                )
                != tile_height
            ):
                raise RuntimeError(
                    (
                        "Turntable still dimensions "
                        "are inconsistent."
                    )
                )

        columns = min(
            4,
            len(
                images
            ),
        )

        rows = (
            len(
                images
            )
            + columns
            - 1
        ) // columns

        sheet_width = (
            tile_width
            * columns
        )

        sheet_height = (
            tile_height
            * rows
        )

        sheet_pixels = (
            array(
                "f",
                [
                    0.0
                ],
            )
            * (
                sheet_width
                * sheet_height
                * 4
            )
        )

        tile_values = (
            tile_width
            * tile_height
            * 4
        )

        row_values = (
            tile_width
            * 4
        )

        for (
            index,
            image,
        ) in enumerate(
            images
        ):
            pixels = (
                array(
                    "f",
                    [
                        0.0
                    ],
                )
                * tile_values
            )

            image.pixels.foreach_get(
                pixels
            )

            column = (
                index
                % columns
            )

            row = (
                index
                // columns
            )

            destination_tile_row = (
                rows
                - 1
                - row
            )

            for local_y in range(
                tile_height
            ):
                source_start = (
                    local_y
                    * row_values
                )

                source_end = (
                    source_start
                    + row_values
                )

                destination_y = (
                    destination_tile_row
                    * tile_height
                    + local_y
                )

                destination_start = (
                    (
                        destination_y
                        * sheet_width
                        + column
                        * tile_width
                    )
                    * 4
                )

                destination_end = (
                    destination_start
                    + row_values
                )

                sheet_pixels[
                    destination_start:
                    destination_end
                ] = (
                    pixels[
                        source_start:
                        source_end
                    ]
                )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        contact = (
            bpy.data.images.new(
                name=(
                    "BPT_ContactSheet"
                ),
                width=(
                    sheet_width
                ),
                height=(
                    sheet_height
                ),
                alpha=True,
            )
        )

        try:
            contact.pixels.foreach_set(
                sheet_pixels
            )

            contact.filepath_raw = str(
                output_path.resolve()
            )

            contact.file_format = (
                "PNG"
            )

            contact.save()

        finally:
            bpy.data.images.remove(
                contact
            )

    finally:
        for image in (
            images
        ):
            if (
                image.name
                in bpy.data.images
            ):
                bpy.data.images.remove(
                    image
                )


# =========================================================
# Reusable API
# =========================================================
