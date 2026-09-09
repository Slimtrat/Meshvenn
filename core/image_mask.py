from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class BinaryMask:
    width: int
    height: int
    values: bytes

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("Mask width must be greater than zero.")
        if self.height <= 0:
            raise ValueError("Mask height must be greater than zero.")

        expected_size = self.width * self.height
        raw = self.values

        if not isinstance(raw, bytes):
            raw = bytes(1 if value else 0 for value in raw)
            object.__setattr__(self, "values", raw)

        if len(raw) != expected_size:
            raise ValueError(
                f"Mask contains {len(raw)} values, expected {expected_size}."
            )

    def get(self, x: int, y: int) -> bool:
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return False
        return bool(self.values[y * self.width + x])

    @property
    def occupied_count(self) -> int:
        return sum(self.values)

    def flipped_x(self) -> "BinaryMask":
        source = self.values
        width = self.width
        result = bytearray(len(source))

        for y in range(self.height):
            row_start = y * width
            row = source[row_start:row_start + width]
            result[row_start:row_start + width] = row[::-1]

        return BinaryMask(self.width, self.height, bytes(result))



def rgba_to_mask(
    pixels: Sequence[float],
    width: int,
    height: int,
    alpha_threshold: float = 0.1,
) -> BinaryMask:
    expected_length = width * height * 4
    if len(pixels) != expected_length:
        raise ValueError(
            f"Expected {expected_length} RGBA values, received {len(pixels)}."
        )

    values = bytearray(width * height)
    target = 0
    for index in range(3, expected_length, 4):
        values[target] = 1 if pixels[index] >= alpha_threshold else 0
        target += 1

    return BinaryMask(width, height, bytes(values))
