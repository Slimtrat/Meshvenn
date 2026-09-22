from __future__ import annotations

from .shared import BinaryMask, array

def _largest_component(
    foreground: bytearray,
    width: int,
    height: int,
) -> list[int]:
    """
    Return indices belonging to the largest
    4-connected foreground component.

    Uses bytearray + list rather than Python
    sets to avoid large per-pixel objects.
    """

    pixel_count = (
        width
        * height
    )

    visited = bytearray(
        pixel_count
    )

    largest: list[int] = []

    for start in range(
        pixel_count
    ):
        if (
            visited[start]
            or not foreground[start]
        ):
            continue

        visited[start] = 1

        stack = [
            start
        ]

        component: list[int] = []

        while stack:
            index = (
                stack.pop()
            )

            component.append(
                index
            )

            x = (
                index
                % width
            )

            if x > 0:
                neighbor = (
                    index
                    - 1
                )

                if (
                    foreground[
                        neighbor
                    ]
                    and not visited[
                        neighbor
                    ]
                ):
                    visited[
                        neighbor
                    ] = 1

                    stack.append(
                        neighbor
                    )

            if (
                x + 1
                < width
            ):
                neighbor = (
                    index
                    + 1
                )

                if (
                    foreground[
                        neighbor
                    ]
                    and not visited[
                        neighbor
                    ]
                ):
                    visited[
                        neighbor
                    ] = 1

                    stack.append(
                        neighbor
                    )

            if index >= width:
                neighbor = (
                    index
                    - width
                )

                if (
                    foreground[
                        neighbor
                    ]
                    and not visited[
                        neighbor
                    ]
                ):
                    visited[
                        neighbor
                    ] = 1

                    stack.append(
                        neighbor
                    )

            neighbor = (
                index
                + width
            )

            if (
                neighbor
                < pixel_count
                and foreground[
                    neighbor
                ]
                and not visited[
                    neighbor
                ]
            ):
                visited[
                    neighbor
                ] = 1

                stack.append(
                    neighbor
                )

        if (
            len(component)
            > len(largest)
        ):
            largest = (
                component
            )

    return largest

def _copy_cell_pixels(
    sheet_pixels: array,
    sheet_width: int,
    bbox: tuple[
        int,
        int,
        int,
        int,
    ],
) -> tuple[
    array,
    int,
    int,
]:
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

    rgba = array(
        "f",
        [0.0],
    ) * (
        width
        * height
        * 4
    )

    row_float_count = (
        width
        * 4
    )

    for local_y in range(
        height
    ):
        source_pixel = (
            (
                y0
                + local_y
            )
            * sheet_width
            + x0
        )

        source_start = (
            source_pixel
            * 4
        )

        source_end = (
            source_start
            + row_float_count
        )

        target_start = (
            local_y
            * row_float_count
        )

        target_end = (
            target_start
            + row_float_count
        )

        rgba[
            target_start:
            target_end
        ] = sheet_pixels[
            source_start:
            source_end
        ]

    return (
        rgba,
        width,
        height,
    )

def _foreground_from_rgba(
    rgba: array,
    width: int,
    height: int,
    *,
    white_threshold: float,
) -> bytearray:
    pixel_count = (
        width
        * height
    )

    foreground = bytearray(
        pixel_count
    )

    source_index = 0

    for pixel_index in range(
        pixel_count
    ):
        red = rgba[
            source_index
        ]

        green = rgba[
            source_index + 1
        ]

        blue = rgba[
            source_index + 2
        ]

        alpha = rgba[
            source_index + 3
        ]

        foreground[
            pixel_index
        ] = (
            1
            if (
                alpha > 0.01
                and not (
                    red
                    >= white_threshold
                    and green
                    >= white_threshold
                    and blue
                    >= white_threshold
                )
            )
            else 0
        )

        source_index += 4

    return foreground

def _apply_component_alpha(
    rgba: array,
    width: int,
    height: int,
    component: list[int],
    *,
    valid: bool,
) -> bytearray:
    pixel_count = (
        width
        * height
    )

    keep = bytearray(
        pixel_count
    )

    if valid:
        for index in component:
            keep[index] = 1

    for pixel_index in range(
        pixel_count
    ):
        if keep[
            pixel_index
        ]:
            continue

        rgba[
            pixel_index
            * 4
            + 3
        ] = 0.0

    return keep

def _mask_from_component(
    rgba: array,
    keep: bytearray,
    width: int,
    height: int,
    *,
    alpha_threshold: float,
) -> BinaryMask:
    pixel_count = (
        width
        * height
    )

    values = bytearray(
        pixel_count
    )

    alpha_index = 3

    for pixel_index in range(
        pixel_count
    ):
        if (
            keep[pixel_index]
            and rgba[
                alpha_index
            ]
            >= alpha_threshold
        ):
            values[
                pixel_index
            ] = 1

        alpha_index += 4

    return BinaryMask(
        width=width,
        height=height,
        values=bytes(
            values
        ),
    )
