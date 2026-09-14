from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias

from .constants import *
from .models import *
from .primitives import *

@dataclass
class TextureBuffer:
    """
    Bottom-left-origin floating point RGBA texture.

    Pixel index:

        ((y * width) + x) * 4

    This intentionally matches Blender image.pixels.
    """

    width: int

    height: int

    pixels: array

    def __post_init__(
        self,
    ) -> None:
        if (
            self.width <= 0
            or self.height <= 0
        ):
            raise ValueError(
                (
                    "Texture dimensions "
                    "must be positive."
                )
            )

        expected = (
            self.width
            * self.height
            * COLOR_CHANNEL_COUNT
        )

        if len(
            self.pixels
        ) != expected:
            raise ValueError(
                (
                    "Texture pixel buffer "
                    "length mismatch. "
                    f"Expected {expected}, "
                    f"received "
                    f"{len(self.pixels)}."
                )
            )

    @classmethod
    def filled(
        cls,
        width: int,
        height: int,
        color: RGBA,
    ) -> "TextureBuffer":
        pixel_count = (
            int(
                width
            )
            * int(
                height
            )
        )

        pixels = array(
            "f",
        )

        pixels.extend(
            color
            * pixel_count
        )

        return cls(
            width=int(
                width
            ),
            height=int(
                height
            ),
            pixels=pixels,
        )

    @property
    def pixel_count(
        self,
    ) -> int:
        return (
            self.width
            * self.height
        )

    def _offset(
        self,
        x: int,
        y: int,
    ) -> int:
        if (
            x < 0
            or x >= self.width
            or y < 0
            or y >= self.height
        ):
            raise IndexError(
                (
                    "Texture coordinates "
                    f"outside image: "
                    f"({x}, {y})."
                )
            )

        return (
            (
                y
                * self.width
                + x
            )
            * COLOR_CHANNEL_COUNT
        )

    def rgba(
        self,
        x: int,
        y: int,
    ) -> RGBA:
        offset = (
            self._offset(
                x,
                y,
            )
        )

        return (
            float(
                self.pixels[
                    offset
                ]
            ),
            float(
                self.pixels[
                    offset + 1
                ]
            ),
            float(
                self.pixels[
                    offset + 2
                ]
            ),
            float(
                self.pixels[
                    offset + 3
                ]
            ),
        )

    def set_rgba(
        self,
        x: int,
        y: int,
        color: RGBA,
    ) -> None:
        offset = (
            self._offset(
                x,
                y,
            )
        )

        self.pixels[
            offset
        ] = color[0]

        self.pixels[
            offset + 1
        ] = color[1]

        self.pixels[
            offset + 2
        ] = color[2]

        self.pixels[
            offset + 3
        ] = color[3]

    def copy_pixel(
        self,
        source_index: int,
        destination_index: int,
    ) -> None:
        source_offset = (
            source_index
            * COLOR_CHANNEL_COUNT
        )

        destination_offset = (
            destination_index
            * COLOR_CHANNEL_COUNT
        )

        for channel in range(
            COLOR_CHANNEL_COUNT
        ):
            self.pixels[
                destination_offset
                + channel
            ] = (
                self.pixels[
                    source_offset
                    + channel
                ]
            )


# =========================================================
# Statistics
# =========================================================

@dataclass(frozen=True)
class UVBakeStats:
    triangle_count: int

    rasterized_triangles: int

    degenerate_triangles: int

    clipped_triangles: int

    outside_triangles: int

    covered_pixels: int

    padded_pixels: int

    overlap_pixels: int

    surface_samples: int

    fallback_samples: int

    selected_source_samples: int

    texture_width: int

    texture_height: int

    samples_per_axis: int

    padding_pixels: int

    @property
    def texture_pixels(
        self,
    ) -> int:
        return (
            self.texture_width
            * self.texture_height
        )

    @property
    def filled_pixels(
        self,
    ) -> int:
        return (
            self.covered_pixels
            + self.padded_pixels
        )

    @property
    def uncovered_pixels(
        self,
    ) -> int:
        return max(
            0,
            self.texture_pixels
            - self.filled_pixels,
        )

    @property
    def coverage_ratio(
        self,
    ) -> float:
        if self.texture_pixels <= 0:
            return 0.0

        return (
            float(
                self.covered_pixels
            )
            / float(
                self.texture_pixels
            )
        )


# =========================================================
# Result
# =========================================================

@dataclass(frozen=True)
class UVBakeResult:
    texture: TextureBuffer

    stats: UVBakeStats

    # Original rasterized island pixels.
    coverage: bytes

    # Coverage + texture padding.
    filled: bytes

    def is_covered(
        self,
        x: int,
        y: int,
    ) -> bool:
        index = (
            y
            * self.texture.width
            + x
        )

        return bool(
            self.coverage[
                index
            ]
        )

    def is_filled(
        self,
        x: int,
        y: int,
    ) -> bool:
        index = (
            y
            * self.texture.width
            + x
        )

        return bool(
            self.filled[
                index
            ]
        )


# =========================================================
# Progress
# =========================================================

@dataclass(frozen=True)
class UVBakeProgress:
    completed_triangles: int

    total_triangles: int

    @property
    def fraction(
        self,
    ) -> float:
        if self.total_triangles <= 0:
            return 1.0

        return clamp01(
            float(
                self.completed_triangles
            )
            / float(
                self.total_triangles
            )
        )


UVBakeProgressCallback: TypeAlias = Callable[
    [
        UVBakeProgress
    ],
    None,
]


# =========================================================
# Internal raster statistics
# =========================================================
