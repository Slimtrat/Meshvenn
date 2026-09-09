from __future__ import annotations

from typing import Final


# ---------------------------------------------------------
# Types
# ---------------------------------------------------------

NormalizedRange = tuple[
    float,
    float,
]

CellSpec = tuple[
    str,
    int,
    int,
    float,
    float,
]


# ---------------------------------------------------------
# Projection Tool presheet v1 layout
# ---------------------------------------------------------
#
# Coordinates are normalized against the complete
# Projection Tool sheet.
#
# Columns are expressed from left to right.
#
# Rows use top/bottom coordinates measured from
# the top of the source image.
#
# The helper below converts them to Blender image
# coordinates, whose origin is at the bottom-left.
# ---------------------------------------------------------

PRESHEET_V1_COLUMNS: Final[
    tuple[
        NormalizedRange,
        ...,
    ]
] = (
    (
        0.016,
        0.164,
    ),
    (
        0.169,
        0.317,
    ),
    (
        0.324,
        0.472,
    ),
    (
        0.478,
        0.626,
    ),
    (
        0.632,
        0.780,
    ),
)


PRESHEET_V1_ROWS: Final[
    tuple[
        NormalizedRange,
        ...,
    ]
] = (
    (
        0.158,
        0.432,
    ),
    (
        0.525,
        0.801,
    ),
)


# ---------------------------------------------------------
# Camera/view specification
# ---------------------------------------------------------
#
# Tuple format:
#
# (
#     name,
#     column,
#     row,
#     azimuth_degrees,
#     elevation_degrees,
# )
#
# This is intentionally shared between:
#
# - reference sheet extraction;
# - native reconstruction;
# - reconstructed projection sheet rendering.
#
# This guarantees that the before and after sheets use
# exactly the same view convention.
# ---------------------------------------------------------

CELL_SPECS: Final[
    tuple[
        CellSpec,
        ...,
    ]
] = (
    (
        "000",
        0,
        0,
        0.0,
        0.0,
    ),
    (
        "045",
        1,
        0,
        45.0,
        0.0,
    ),
    (
        "090",
        2,
        0,
        90.0,
        0.0,
    ),
    (
        "135",
        3,
        0,
        135.0,
        0.0,
    ),
    (
        "180",
        4,
        0,
        180.0,
        0.0,
    ),
    (
        "225",
        0,
        1,
        225.0,
        0.0,
    ),
    (
        "270",
        1,
        1,
        270.0,
        0.0,
    ),
    (
        "315",
        2,
        1,
        315.0,
        0.0,
    ),
    (
        "TOP",
        3,
        1,
        0.0,
        90.0,
    ),
    (
        "BOT",
        4,
        1,
        0.0,
        -90.0,
    ),
)


# ---------------------------------------------------------
# Pixel geometry
# ---------------------------------------------------------

def pixel_bbox(
    image_width: int,
    image_height: int,
    column: int,
    row: int,
) -> tuple[
    int,
    int,
    int,
    int,
]:
    """
    Return the pixel bounding box of a Projection Tool cell.

    The returned coordinates use Blender image coordinates:

        x0, y0, x1, y1

    with the image origin at the bottom-left.
    """

    if image_width <= 0:
        raise ValueError(
            "image_width must be greater than zero"
        )

    if image_height <= 0:
        raise ValueError(
            "image_height must be greater than zero"
        )

    if not (
        0
        <= column
        < len(
            PRESHEET_V1_COLUMNS
        )
    ):
        raise ValueError(
            (
                "Invalid presheet column: "
                f"{column}"
            )
        )

    if not (
        0
        <= row
        < len(
            PRESHEET_V1_ROWS
        )
    ):
        raise ValueError(
            (
                "Invalid presheet row: "
                f"{row}"
            )
        )

    (
        x0_normalized,
        x1_normalized,
    ) = PRESHEET_V1_COLUMNS[
        column
    ]

    (
        top_normalized,
        bottom_normalized,
    ) = PRESHEET_V1_ROWS[
        row
    ]

    x0 = round(
        x0_normalized
        * image_width
    )

    x1 = round(
        x1_normalized
        * image_width
    )

    y0 = round(
        (
            1.0
            - bottom_normalized
        )
        * image_height
    )

    y1 = round(
        (
            1.0
            - top_normalized
        )
        * image_height
    )

    return (
        x0,
        y0,
        x1,
        y1,
    )