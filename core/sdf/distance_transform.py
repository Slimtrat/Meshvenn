from __future__ import annotations

import math
from array import array
from typing import Sequence

from ..image_mask import BinaryMask
from .utils import require_finite


def distance_transform_1d(values: Sequence[float], *, spacing: float) -> list[float]:
    """Exact lower-envelope squared-distance transform."""
    count = len(values)
    if count == 0:
        return []
    spacing = require_finite(spacing, name="spacing")
    if spacing <= 0.0:
        raise ValueError("spacing must be greater than zero.")

    finite_sites = [i for i, value in enumerate(values) if math.isfinite(float(value))]
    if not finite_sites:
        return [math.inf] * count

    sites = [finite_sites[0]]
    starts = [-math.inf]

    def intersection(left_index: int, right_index: int) -> float:
        left_x = float(left_index) * spacing
        right_x = float(right_index) * spacing
        numerator = (
            float(values[right_index]) + right_x * right_x
            - float(values[left_index]) - left_x * left_x
        )
        return numerator / (2.0 * (right_x - left_x))

    for site in finite_sites[1:]:
        start = intersection(sites[-1], site)
        while len(sites) > 1 and start <= starts[-1]:
            sites.pop()
            starts.pop()
            start = intersection(sites[-1], site)
        sites.append(site)
        starts.append(start)

    result = [0.0] * count
    active = 0
    for index in range(count):
        x = float(index) * spacing
        while active + 1 < len(sites) and x >= starts[active + 1]:
            active += 1
        site = sites[active]
        delta = x - float(site) * spacing
        result[index] = float(values[site]) + delta * delta
    return result


def squared_distance_to_mask_value(
    mask: BinaryMask,
    *,
    target_inside: bool,
    horizontal_spacing: float,
    vertical_spacing: float,
) -> array:
    """Squared distance from every pixel centre to the requested mask state."""
    width, height = int(mask.width), int(mask.height)
    horizontal_spacing = require_finite(horizontal_spacing, name="horizontal_spacing")
    vertical_spacing = require_finite(vertical_spacing, name="vertical_spacing")
    if horizontal_spacing <= 0.0:
        raise ValueError("horizontal_spacing must be greater than zero.")
    if vertical_spacing <= 0.0:
        raise ValueError("vertical_spacing must be greater than zero.")

    intermediate = array("d", [math.inf]) * (width * height)
    for y in range(height):
        row_start = y * width
        row = [
            0.0 if bool(mask.values[row_start + x]) == target_inside else math.inf
            for x in range(width)
        ]
        for x, value in enumerate(distance_transform_1d(row, spacing=horizontal_spacing)):
            intermediate[row_start + x] = value

    result = array("d", [math.inf]) * (width * height)
    for x in range(width):
        column = [intermediate[y * width + x] for y in range(height)]
        for y, value in enumerate(distance_transform_1d(column, spacing=vertical_spacing)):
            result[y * width + x] = value
    return result
