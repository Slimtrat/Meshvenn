from __future__ import annotations

from .shared import BACKGROUND_COLOR, Path, array, bpy
from .render import load_image_pixels

def compose_matrix(
    cells: dict[
        tuple[
            str,
            str,
        ],
        Path,
    ],
    *,
    profiles: list[str],
    columns: list[str],
    output_path: Path,
    gutter: int,
) -> None:
    paths = [
        path
        for path
        in cells.values()
        if path.is_file()
    ]

    if not paths:
        raise RuntimeError(
            (
                "No render images available "
                "for benchmark matrix."
            )
        )

    (
        first_pixels,
        tile_width,
        tile_height,
    ) = (
        load_image_pixels(
            paths[
                0
            ]
        )
    )

    del first_pixels

    column_count = len(
        columns
    )

    row_count = len(
        profiles
    )

    output_width = (
        tile_width
        * column_count
        + gutter
        * max(
            0,
            column_count - 1,
        )
    )

    output_height = (
        tile_height
        * row_count
        + gutter
        * max(
            0,
            row_count - 1,
        )
    )

    destination = (
        array(
            "f",
            BACKGROUND_COLOR,
        )
        * (
            output_width
            * output_height
        )
    )

    row_values = (
        tile_width
        * 4
    )

    for (
        profile_index,
        profile,
    ) in enumerate(
        profiles
    ):
        visual_row = (
            row_count
            - 1
            - profile_index
        )

        destination_y = (
            visual_row
            * (
                tile_height
                + gutter
            )
        )

        for (
            column_index,
            column,
        ) in enumerate(
            columns
        ):
            path = (
                cells.get(
                    (
                        profile,
                        column,
                    )
                )
            )

            if (
                path is None
                or not path.is_file()
            ):
                continue

            (
                source,
                width,
                height,
            ) = (
                load_image_pixels(
                    path
                )
            )

            if (
                width != tile_width
                or height
                != tile_height
            ):
                raise RuntimeError(
                    (
                        "Benchmark render dimensions "
                        "are inconsistent."
                    )
                )

            destination_x = (
                column_index
                * (
                    tile_width
                    + gutter
                )
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

                destination_start = (
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

                destination_end = (
                    destination_start
                    + row_values
                )

                destination[
                    destination_start:
                    destination_end
                ] = (
                    source[
                        source_start:
                        source_end
                    ]
                )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = (
        bpy.data.images.new(
            name=(
                "MeshvennUVResolutionBenchmark"
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
