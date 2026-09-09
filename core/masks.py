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


def resize_mask_nearest(
    mask: BinaryMask,
    width: int,
    height: int,
) -> BinaryMask:
    if width <= 0:
        raise ValueError("Target width must be greater than zero.")
    if height <= 0:
        raise ValueError("Target height must be greater than zero.")
    if width == mask.width and height == mask.height:
        return mask

    source = mask.values
    source_width = mask.width
    source_height = mask.height

    x_map = [
        min(int(x * source_width / width), source_width - 1)
        for x in range(width)
    ]
    y_map = [
        min(int(y * source_height / height), source_height - 1)
        for y in range(height)
    ]

    result = bytearray(width * height)
    target_index = 0

    for source_y in y_map:
        row_start = source_y * source_width
        for source_x in x_map:
            result[target_index] = source[row_start + source_x]
            target_index += 1

    return BinaryMask(width, height, bytes(result))


def fit_mask_preserve_aspect(
    mask: BinaryMask,
    width: int,
    height: int,
) -> BinaryMask:
    if width <= 0:
        raise ValueError("Target width must be greater than zero.")
    if height <= 0:
        raise ValueError("Target height must be greater than zero.")

    scale = min(width / mask.width, height / mask.height)
    fitted_width = max(1, min(width, round(mask.width * scale)))
    fitted_height = max(1, min(height, round(mask.height * scale)))

    resized = resize_mask_nearest(mask, fitted_width, fitted_height)
    offset_x = (width - fitted_width) // 2
    offset_y = (height - fitted_height) // 2

    values = bytearray(width * height)
    source = resized.values

    for y in range(fitted_height):
        source_start = y * fitted_width
        target_start = (offset_y + y) * width + offset_x
        values[target_start:target_start + fitted_width] = (
            source[source_start:source_start + fitted_width]
        )

    return BinaryMask(width, height, bytes(values))


def find_mask_bounds(
    mask: BinaryMask,
) -> tuple[int, int, int, int] | None:
    width = mask.width
    values = mask.values

    min_x = width
    min_y = mask.height
    max_x = -1
    max_y = -1

    for index, occupied in enumerate(values):
        if not occupied:
            continue

        y, x = divmod(index, width)
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y

    if max_x < 0:
        return None

    return min_x, max_x, min_y, max_y


def crop_mask_to_content(
    mask: BinaryMask,
    *,
    padding: int = 0,
) -> BinaryMask:
    if padding < 0:
        raise ValueError("Padding must be zero or greater.")

    bounds = find_mask_bounds(mask)
    if bounds is None:
        return mask

    min_x, max_x, min_y, max_y = bounds
    min_x = max(0, min_x - padding)
    max_x = min(mask.width - 1, max_x + padding)
    min_y = max(0, min_y - padding)
    max_y = min(mask.height - 1, max_y + padding)

    width = max_x - min_x + 1
    height = max_y - min_y + 1
    result = bytearray(width * height)
    source = mask.values

    for target_y, source_y in enumerate(range(min_y, max_y + 1)):
        source_start = source_y * mask.width + min_x
        target_start = target_y * width
        result[target_start:target_start + width] = (
            source[source_start:source_start + width]
        )

    return BinaryMask(width, height, bytes(result))


def normalize_mask(
    mask: BinaryMask,
    width: int,
    height: int,
    *,
    crop_content: bool = False,
    crop_padding: int = 0,
) -> BinaryMask:
    working_mask = mask
    if crop_content:
        working_mask = crop_mask_to_content(
            working_mask,
            padding=crop_padding,
        )

    return fit_mask_preserve_aspect(working_mask, width, height)


def enforce_horizontal_symmetry(mask: BinaryMask) -> BinaryMask:
    width = mask.width
    values = bytearray(mask.values)
    half_width = (width + 1) // 2

    for y in range(mask.height):
        row = y * width
        for x in range(half_width):
            opposite_x = width - 1 - x
            occupied = values[row + x] or values[row + opposite_x]
            values[row + x] = occupied
            values[row + opposite_x] = occupied

    return BinaryMask(mask.width, mask.height, bytes(values))
