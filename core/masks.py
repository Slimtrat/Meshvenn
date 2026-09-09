from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class BinaryMask:
    width: int
    height: int
    values: tuple[bool, ...]

    def __post_init__(self) -> None:
        expected_size = self.width * self.height

        if self.width <= 0:
            raise ValueError("Mask width must be greater than zero.")

        if self.height <= 0:
            raise ValueError("Mask height must be greater than zero.")

        if len(self.values) != expected_size:
            raise ValueError(
                f"Mask contains {len(self.values)} values, "
                f"expected {expected_size}."
            )

    def get(self, x: int, y: int) -> bool:
        if x < 0 or x >= self.width:
            return False

        if y < 0 or y >= self.height:
            return False

        return self.values[y * self.width + x]

    def flipped_x(self) -> "BinaryMask":
        result: list[bool] = []

        for y in range(self.height):
            for x in range(self.width):
                result.append(
                    self.get(self.width - 1 - x, y)
                )

        return BinaryMask(
            width=self.width,
            height=self.height,
            values=tuple(result),
        )


def rgba_to_mask(
    pixels: Sequence[float],
    width: int,
    height: int,
    alpha_threshold: float = 0.1,
) -> BinaryMask:
    expected_length = width * height * 4

    if len(pixels) != expected_length:
        raise ValueError(
            f"Expected {expected_length} RGBA values, "
            f"received {len(pixels)}."
        )

    values: list[bool] = []

    for index in range(0, len(pixels), 4):
        alpha = pixels[index + 3]

        values.append(
            alpha >= alpha_threshold
        )

    return BinaryMask(
        width=width,
        height=height,
        values=tuple(values),
    )


def resize_mask_nearest(
    mask: BinaryMask,
    width: int,
    height: int,
) -> BinaryMask:
    if width <= 0:
        raise ValueError("Target width must be greater than zero.")

    if height <= 0:
        raise ValueError("Target height must be greater than zero.")

    values: list[bool] = []

    for y in range(height):
        source_y = min(
            int(y * mask.height / height),
            mask.height - 1,
        )

        for x in range(width):
            source_x = min(
                int(x * mask.width / width),
                mask.width - 1,
            )

            values.append(
                mask.get(source_x, source_y)
            )

    return BinaryMask(
        width=width,
        height=height,
        values=tuple(values),
    )


def enforce_horizontal_symmetry(
    mask: BinaryMask,
) -> BinaryMask:
    values = list(mask.values)

    half_width = (mask.width + 1) // 2

    for y in range(mask.height):
        for x in range(half_width):
            opposite_x = mask.width - 1 - x

            occupied = (
                mask.get(x, y)
                or mask.get(opposite_x, y)
            )

            values[y * mask.width + x] = occupied
            values[y * mask.width + opposite_x] = occupied

    return BinaryMask(
        width=mask.width,
        height=mask.height,
        values=tuple(values),
    )