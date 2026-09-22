from __future__ import annotations

from array import array
from pathlib import Path
from typing import Any

import bpy

from .config import BACKGROUND_COLOR
from .images import _image_size, _load_image_pixels

# =========================================================
# Final matrix
# =========================================================

def build_comparison_matrix(
    cells: dict[
        tuple[
            str,
            str,
        ],
        Path,
    ],
    *,
    profiles: list[str],
    implementations: list[str],
    output_path: Path,
    gutter: int,
) -> dict[str, Any]:
    """
    Layout:

                           implementations →

            projected-color-v1.2 | uv-bake-v2

        L2      contact sheet    | contact sheet

        L4      contact sheet    | contact sheet

        L8      contact sheet    | contact sheet

        L10     contact sheet    | contact sheet


    No Pillow/ImageMagick dependency is required.

    Composition happens directly through Blender image
    buffers.
    """

    available_paths = [
        path
        for path
        in cells.values()
        if path.is_file()
    ]

    if not available_paths:
        raise RuntimeError(
            (
                "No rendered contact sheet "
                "is available for composition."
            )
        )

    (
        tile_width,
        tile_height,
    ) = (
        _image_size(
            available_paths[
                0
            ]
        )
    )

    # -----------------------------------------------------
    # Every implementation must use the exact same
    # turntable dimensions.
    # -----------------------------------------------------

    for path in (
        available_paths[
            1:
        ]
    ):
        (
            width,
            height,
        ) = (
            _image_size(
                path
            )
        )

        if (
            width != tile_width
            or height != tile_height
        ):
            raise RuntimeError(
                (
                    "Contact-sheet dimensions "
                    "are inconsistent.\n"
                    f"Expected: "
                    f"{tile_width}x{tile_height}\n"
                    f"Received: "
                    f"{width}x{height}\n"
                    f"File: {path}"
                )
            )

    columns = len(
        implementations
    )

    rows = len(
        profiles
    )

    output_width = (
        columns
        * tile_width
        + max(
            0,
            columns - 1,
        )
        * gutter
    )

    output_height = (
        rows
        * tile_height
        + max(
            0,
            rows - 1,
        )
        * gutter
    )

    pixel_count = (
        output_width
        * output_height
    )

    destination = (
        array(
            "f",
            BACKGROUND_COLOR,
        )
        * pixel_count
    )

    source_row_values = (
        tile_width
        * 4
    )

    layout_cells = []

    # -----------------------------------------------------
    # Blender images have bottom-left pixel origin.
    #
    # profiles[0] must appear visually on TOP, so rows are
    # reversed when calculating destination Y.
    # -----------------------------------------------------

    for (
        profile_index,
        profile,
    ) in enumerate(
        profiles
    ):
        destination_row = (
            rows
            - 1
            - profile_index
        )

        destination_y = (
            destination_row
            * (
                tile_height
                + gutter
            )
        )

        for (
            implementation_index,
            implementation,
        ) in enumerate(
            implementations
        ):
            destination_x = (
                implementation_index
                * (
                    tile_width
                    + gutter
                )
            )

            key = (
                profile,
                implementation,
            )

            source_path = (
                cells.get(
                    key
                )
            )

            cell_info = {
                "profile": profile,

                "implementation": (
                    implementation
                ),

                "column": (
                    implementation_index
                ),

                "row": (
                    profile_index
                ),

                "x": (
                    destination_x
                ),

                "y": (
                    destination_y
                ),

                "width": (
                    tile_width
                ),

                "height": (
                    tile_height
                ),

                "image": (
                    str(
                        source_path
                    )
                    if source_path
                    is not None
                    else None
                ),

                "present": False,
            }

            layout_cells.append(
                cell_info
            )

            # ---------------------------------------------
            # Missing variants are deliberately left with
            # the neutral background when
            # --continue-on-error is active.
            # ---------------------------------------------

            if (
                source_path is None
                or not source_path.is_file()
            ):
                continue

            (
                source,
                width,
                height,
            ) = (
                _load_image_pixels(
                    source_path
                )
            )

            if (
                width != tile_width
                or height
                != tile_height
            ):
                raise RuntimeError(
                    (
                        "Unexpected source image "
                        "dimensions during copy."
                    )
                )

            for local_y in range(
                tile_height
            ):
                source_start = (
                    local_y
                    * source_row_values
                )

                source_end = (
                    source_start
                    + source_row_values
                )

                target_start = (
                    (
                        (
                            destination_y
                            + local_y
                        )
                        * output_width
                        + destination_x
                    )
                    * 4
                )

                target_end = (
                    target_start
                    + source_row_values
                )

                destination[
                    target_start:
                    target_end
                ] = (
                    source[
                        source_start:
                        source_end
                    ]
                )

            cell_info[
                "present"
            ] = True

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = (
        bpy.data.images.new(
            name=(
                "MeshvennMaterialComparison"
            ),
            width=(
                output_width
            ),
            height=(
                output_height
            ),
            alpha=True,
        )
    )

    try:
        image.pixels.foreach_set(
            destination
        )

        image.filepath_raw = str(
            output_path.resolve()
        )

        image.file_format = (
            "PNG"
        )

        image.save()

    finally:
        bpy.data.images.remove(
            image
        )

    if not output_path.is_file():
        raise RuntimeError(
            (
                "Comparison matrix was "
                "not generated."
            )
        )

    return {
        "image": str(
            output_path
        ),

        "width": (
            output_width
        ),

        "height": (
            output_height
        ),

        "tile_width": (
            tile_width
        ),

        "tile_height": (
            tile_height
        ),

        "gutter": (
            gutter
        ),

        "rows": list(
            profiles
        ),

        "columns": list(
            implementations
        ),

        "cells": (
            layout_cells
        ),
    }
