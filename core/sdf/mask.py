from __future__ import annotations

import math
from array import array
from dataclasses import dataclass

from ..image_mask import BinaryMask
from .distance_transform import squared_distance_to_mask_value
from .utils import clamp, lerp, require_finite


@dataclass(frozen=True)
class SignedDistanceMask:
    """Continuous signed-distance representation of one silhouette."""

    width: int
    height: int
    values: array
    horizontal_extent: float
    vertical_extent: float
    occupied_count: int

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("Signed-distance mask width must be positive.")
        if self.height <= 0:
            raise ValueError("Signed-distance mask height must be positive.")
        horizontal_extent = require_finite(self.horizontal_extent, name="horizontal_extent")
        vertical_extent = require_finite(self.vertical_extent, name="vertical_extent")
        if horizontal_extent <= 0.0:
            raise ValueError("horizontal_extent must be positive.")
        if vertical_extent <= 0.0:
            raise ValueError("vertical_extent must be positive.")
        expected_count = self.width * self.height
        copied = array("f", self.values)
        if len(copied) != expected_count:
            raise ValueError(
                f"Signed-distance mask contains {len(copied)} values, expected {expected_count}."
            )
        if any(not math.isfinite(float(value)) for value in copied):
            raise ValueError("Signed-distance mask contains a non-finite value.")
        occupied_count = int(self.occupied_count)
        if occupied_count < 0 or occupied_count > expected_count:
            raise ValueError("occupied_count is outside the valid mask range.")
        object.__setattr__(self, "horizontal_extent", horizontal_extent)
        object.__setattr__(self, "vertical_extent", vertical_extent)
        object.__setattr__(self, "occupied_count", occupied_count)
        object.__setattr__(self, "values", copied)

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    @property
    def domain_width(self) -> float:
        return self.horizontal_extent * 2.0

    @property
    def domain_height(self) -> float:
        return self.vertical_extent * 2.0

    @property
    def horizontal_spacing(self) -> float:
        return self.domain_width if self.width <= 1 else self.domain_width / float(self.width - 1)

    @property
    def vertical_spacing(self) -> float:
        return self.domain_height if self.height <= 1 else self.domain_height / float(self.height - 1)

    @property
    def empty(self) -> bool:
        return self.occupied_count == 0

    @property
    def full(self) -> bool:
        return self.occupied_count == self.pixel_count

    def get(self, x: int, y: int) -> float:
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            raise IndexError("Signed-distance mask coordinate outside bounds.")
        return float(self.values[y * self.width + x])

    def _sample_clamped_uv(self, u: float, v: float) -> float:
        u, v = clamp(u, 0.0, 1.0), clamp(v, 0.0, 1.0)
        x = 0.0 if self.width <= 1 else u * float(self.width - 1)
        y = 0.0 if self.height <= 1 else v * float(self.height - 1)
        x0, y0 = int(math.floor(x)), int(math.floor(y))
        x1, y1 = min(x0 + 1, self.width - 1), min(y0 + 1, self.height - 1)
        tx, ty = x - float(x0), y - float(y0)
        bottom = lerp(self.get(x0, y0), self.get(x1, y0), tx)
        top = lerp(self.get(x0, y1), self.get(x1, y1), tx)
        return lerp(bottom, top, ty)

    def sample_uv(self, u: float, v: float) -> float:
        """Sample continuous signed distance in projection UV."""
        u, v = require_finite(u, name="u"), require_finite(v, name="v")
        edge_value = self._sample_clamped_uv(clamp(u, 0.0, 1.0), clamp(v, 0.0, 1.0))
        if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
            return edge_value
        outside_x = -u * self.domain_width if u < 0.0 else (u - 1.0) * self.domain_width if u > 1.0 else 0.0
        outside_y = -v * self.domain_height if v < 0.0 else (v - 1.0) * self.domain_height if v > 1.0 else 0.0
        return math.hypot(outside_x, outside_y) + max(0.0, edge_value)


def build_signed_distance_mask(
    mask: BinaryMask,
    *,
    horizontal_extent: float = 1.0,
    vertical_extent: float = 1.0,
) -> SignedDistanceMask:
    """Convert a BinaryMask into an exact Euclidean signed distance field."""
    if not isinstance(mask, BinaryMask):
        raise TypeError("mask must be BinaryMask.")
    horizontal_extent = require_finite(horizontal_extent, name="horizontal_extent")
    vertical_extent = require_finite(vertical_extent, name="vertical_extent")
    if horizontal_extent <= 0.0:
        raise ValueError("horizontal_extent must be positive.")
    if vertical_extent <= 0.0:
        raise ValueError("vertical_extent must be positive.")

    width, height = int(mask.width), int(mask.height)
    domain_width, domain_height = horizontal_extent * 2.0, vertical_extent * 2.0
    horizontal_spacing = domain_width / float(width - 1) if width > 1 else domain_width
    vertical_spacing = domain_height / float(height - 1) if height > 1 else domain_height
    distance_to_inside_sq = squared_distance_to_mask_value(
        mask,
        target_inside=True,
        horizontal_spacing=horizontal_spacing,
        vertical_spacing=vertical_spacing,
    )
    distance_to_outside_sq = squared_distance_to_mask_value(
        mask,
        target_inside=False,
        horizontal_spacing=horizontal_spacing,
        vertical_spacing=vertical_spacing,
    )
    output = array("f", [0.0]) * (width * height)
    occupied_count = 0
    empty_fallback_distance = math.hypot(domain_width, domain_height) + max(
        horizontal_spacing, vertical_spacing
    )
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if bool(mask.values[index]):
                occupied_count += 1
                internal_squared = distance_to_outside_sq[index]
                internal_distance = (
                    math.sqrt(max(0.0, internal_squared))
                    if math.isfinite(internal_squared)
                    else math.inf
                )
                border_distance = min(
                    (float(x) + 0.5) * horizontal_spacing,
                    (float(width - 1 - x) + 0.5) * horizontal_spacing,
                    (float(y) + 0.5) * vertical_spacing,
                    (float(height - 1 - y) + 0.5) * vertical_spacing,
                )
                output[index] = -float(min(internal_distance, border_distance))
            else:
                squared = distance_to_inside_sq[index]
                distance = math.sqrt(max(0.0, squared)) if math.isfinite(squared) else empty_fallback_distance
                output[index] = float(distance)
    return SignedDistanceMask(
        width=width,
        height=height,
        values=output,
        horizontal_extent=horizontal_extent,
        vertical_extent=vertical_extent,
        occupied_count=occupied_count,
    )
