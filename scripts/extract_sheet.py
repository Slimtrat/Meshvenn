# scripts/extract_sheet.py

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


GRID_COLUMNS = 5
GRID_ROWS = 2

CELL_NAMES = (
    "000",
    "045",
    "090",
    "135",
    "180",
    "225",
    "270",
    "315",
    "TOP",
    "BOT",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a fixed 5x2 Projection Tool presheet "
            "into individual projection images."
        )
    )

    parser.add_argument(
        "sheet",
        type=Path,
        help="Input sheet.png",
    )

    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory receiving extracted views",
    )

    parser.add_argument(
        "--padding",
        type=int,
        default=0,
        help="Crop this many pixels from each cell edge",
    )

    parser.add_argument(
        "--transparent-white",
        action="store_true",
        help="Convert near-white background pixels to transparency",
    )

    parser.add_argument(
        "--white-threshold",
        type=int,
        default=248,
        help="RGB threshold used by --transparent-white",
    )

    return parser.parse_args()


def calculate_cell_box(
    sheet_width: int,
    sheet_height: int,
    column: int,
    row: int,
) -> tuple[int, int, int, int]:
    left = round(
        column * sheet_width / GRID_COLUMNS
    )

    right = round(
        (column + 1) * sheet_width / GRID_COLUMNS
    )

    top = round(
        row * sheet_height / GRID_ROWS
    )

    bottom = round(
        (row + 1) * sheet_height / GRID_ROWS
    )

    return (
        left,
        top,
        right,
        bottom,
    )


def apply_padding(
    box: tuple[int, int, int, int],
    padding: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = box

    left += padding
    top += padding
    right -= padding
    bottom -= padding

    if right <= left:
        raise ValueError(
            "Padding is too large for cell width."
        )

    if bottom <= top:
        raise ValueError(
            "Padding is too large for cell height."
        )

    return (
        left,
        top,
        right,
        bottom,
    )


def white_to_alpha(
    image: Image.Image,
    threshold: int,
) -> Image.Image:
    rgba = image.convert("RGBA")

    pixels = list(
        rgba.getdata()
    )

    converted = []

    for red, green, blue, alpha in pixels:
        if (
            red >= threshold
            and green >= threshold
            and blue >= threshold
        ):
            converted.append(
                (
                    red,
                    green,
                    blue,
                    0,
                )
            )
        else:
            converted.append(
                (
                    red,
                    green,
                    blue,
                    alpha,
                )
            )

    rgba.putdata(
        converted
    )

    return rgba


def extract_sheet(
    sheet_path: Path,
    output_dir: Path,
    *,
    padding: int = 0,
    transparent_white: bool = False,
    white_threshold: int = 248,
) -> list[Path]:
    if not sheet_path.exists():
        raise FileNotFoundError(
            f"Sheet not found: {sheet_path}"
        )

    if padding < 0:
        raise ValueError(
            "Padding must be >= 0."
        )

    if not 0 <= white_threshold <= 255:
        raise ValueError(
            "White threshold must be between 0 and 255."
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    sheet = Image.open(
        sheet_path
    ).convert("RGBA")

    sheet_width, sheet_height = sheet.size

    outputs: list[Path] = []

    for index, cell_name in enumerate(CELL_NAMES):
        row = index // GRID_COLUMNS
        column = index % GRID_COLUMNS

        box = calculate_cell_box(
            sheet_width,
            sheet_height,
            column,
            row,
        )

        if padding:
            box = apply_padding(
                box,
                padding,
            )

        cell = sheet.crop(
            box
        )

        if transparent_white:
            cell = white_to_alpha(
                cell,
                threshold=white_threshold,
            )

        output_path = (
            output_dir
            / f"{cell_name}.png"
        )

        cell.save(
            output_path,
            format="PNG",
        )

        outputs.append(
            output_path
        )

        print(
            f"[projection-tool] "
            f"{cell_name} -> {output_path}"
        )

    return outputs


def main() -> None:
    args = parse_args()

    outputs = extract_sheet(
        args.sheet.resolve(),
        args.output_dir.resolve(),
        padding=args.padding,
        transparent_white=args.transparent_white,
        white_threshold=args.white_threshold,
    )

    print()
    print(
        f"[projection-tool] "
        f"extracted {len(outputs)} views."
    )


if __name__ == "__main__":
    main()