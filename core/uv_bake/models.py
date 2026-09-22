from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias

from .constants import *
from .primitives import (
    clamp01, _finite_float, _vector2, _vector3, _rgba, _length3, _normalize3,
    _cross3, _subtract3, _interpolate3,
)

@dataclass(frozen=True)
class UVBakeVertex:
    """
    One corner of a triangle participating in texture bake.

    position:
        Mesh-local surface position.

    normal:
        Mesh-local surface normal.

    uv:
        UV coordinates.

        Convention:

            u = 0 -> left
            u = 1 -> right

            v = 0 -> bottom
            v = 1 -> top

    The convention deliberately matches Blender image pixel
    storage and Meshvenn's projection system.
    """

    position: Vector3

    normal: Vector3

    uv: Vector2

    def __post_init__(
        self,
    ) -> None:
        position = _vector3(
            self.position,
            name="position",
        )

        normal = _normalize3(
            _vector3(
                self.normal,
                name="normal",
            )
        )

        uv = _vector2(
            self.uv,
            name="uv",
        )

        object.__setattr__(
            self,
            "position",
            position,
        )

        object.__setattr__(
            self,
            "normal",
            normal,
        )

        object.__setattr__(
            self,
            "uv",
            uv,
        )


# =========================================================
# Bake triangle
# =========================================================

@dataclass(frozen=True)
class UVBakeTriangle:
    """
    One UV-space triangle.

    Blender-specific triangulation belongs to the adapter.

    The core only needs three corners containing:

        position
        normal
        uv
    """

    a: UVBakeVertex

    b: UVBakeVertex

    c: UVBakeVertex

    source_index: int = -1

    @property
    def signed_uv_area_twice(
        self,
    ) -> float:
        ax, ay = (
            self.a.uv
        )

        bx, by = (
            self.b.uv
        )

        cx, cy = (
            self.c.uv
        )

        return (
            (
                bx - ax
            )
            * (
                cy - ay
            )
            - (
                by - ay
            )
            * (
                cx - ax
            )
        )

    @property
    def absolute_uv_area(
        self,
    ) -> float:
        return (
            abs(
                self
                .signed_uv_area_twice
            )
            * 0.5
        )

    @property
    def has_uv_outside_unit_square(
        self,
    ) -> bool:
        for vertex in (
            self.a,
            self.b,
            self.c,
        ):
            (
                u,
                v,
            ) = (
                vertex.uv
            )

            if (
                u < 0.0
                or u > 1.0
                or v < 0.0
                or v > 1.0
            ):
                return True

        return False


# =========================================================
# Surface color sample
# =========================================================

@dataclass(frozen=True)
class SurfaceColorSample:
    """
    Color returned by the surface sampler.

    UV bake deliberately knows nothing about how this color
    was obtained.

    Current adapter:

        position + normal
            ↓
        Projected Color V1.2
            ↓
        SurfaceColorSample

    Future possibilities:

        vertex paint
        procedural material
        neural appearance
        photogrammetry texture
    """

    color: RGBA

    used_fallback: bool = False

    selected_samples: int = 0

    metadata: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "color",
            _rgba(
                self.color,
                name="color",
                clamp=False,
            ),
        )

        selected_samples = int(
            self.selected_samples
        )

        if selected_samples < 0:
            raise ValueError(
                (
                    "selected_samples "
                    "cannot be negative."
                )
            )

        object.__setattr__(
            self,
            "selected_samples",
            selected_samples,
        )


SurfaceColorSampler: TypeAlias = Callable[
    [
        Vector3,
        Vector3,
    ],
    (
        SurfaceColorSample
        | RGBA
    ),
]


# =========================================================
# Bake configuration
# =========================================================

@dataclass(frozen=True)
class UVBakeConfig:
    """
    Generic UV texture bake configuration.

    width / height:
        Texture resolution.

        The product default is currently 512×512.

        Larger explicit sizes remain supported for
        high-quality export.

    padding_pixels:
        Number of texels dilated around baked UV islands.

        Padding is important because bilinear filtering and
        mipmaps sample slightly outside UV island borders.

    samples_per_axis:
        1 -> 1 sample / texel
        2 -> 4 samples / texel
        3 -> 9 samples / texel
        4 -> 16 samples / texel

        Default intentionally remains 1 because projected
        color may perform visibility raycasts for every
        sample.

    background_color:
        Color of texels not occupied by an island or padding.

    clamp_colors:
        Clamp sampled RGBA into [0, 1].

    barycentric_epsilon:
        Numerical tolerance used when classifying samples on
        triangle edges.

    degenerate_uv_epsilon:
        Minimum absolute twice-area of a rasterizable UV
        triangle.
    """

    width: int = (
        DEFAULT_TEXTURE_SIZE
    )

    height: int = (
        DEFAULT_TEXTURE_SIZE
    )

    padding_pixels: int = (
        DEFAULT_PADDING_PIXELS
    )

    samples_per_axis: int = (
        DEFAULT_SAMPLES_PER_AXIS
    )

    background_color: RGBA = (
        DEFAULT_BACKGROUND_COLOR
    )

    clamp_colors: bool = True

    barycentric_epsilon: float = (
        DEFAULT_BARYCENTRIC_EPSILON
    )

    degenerate_uv_epsilon: float = (
        DEFAULT_DEGENERATE_UV_EPSILON
    )

    def validate(
        self,
    ) -> None:
        if (
            not isinstance(
                self.width,
                int,
            )
            or self.width <= 0
            or self.width
            > MAX_TEXTURE_DIMENSION
        ):
            raise ValueError(
                (
                    "Texture width must be "
                    f"between 1 and "
                    f"{MAX_TEXTURE_DIMENSION}."
                )
            )

        if (
            not isinstance(
                self.height,
                int,
            )
            or self.height <= 0
            or self.height
            > MAX_TEXTURE_DIMENSION
        ):
            raise ValueError(
                (
                    "Texture height must be "
                    f"between 1 and "
                    f"{MAX_TEXTURE_DIMENSION}."
                )
            )

        if (
            not isinstance(
                self.padding_pixels,
                int,
            )
            or self.padding_pixels < 0
            or self.padding_pixels
            > MAX_PADDING_PIXELS
        ):
            raise ValueError(
                (
                    "padding_pixels must be "
                    f"between 0 and "
                    f"{MAX_PADDING_PIXELS}."
                )
            )

        if (
            not isinstance(
                self.samples_per_axis,
                int,
            )
            or self.samples_per_axis < 1
            or self.samples_per_axis
            > MAX_SAMPLES_PER_AXIS
        ):
            raise ValueError(
                (
                    "samples_per_axis must be "
                    f"between 1 and "
                    f"{MAX_SAMPLES_PER_AXIS}."
                )
            )

        barycentric_epsilon = (
            _finite_float(
                self.barycentric_epsilon,
                name=(
                    "barycentric_epsilon"
                ),
            )
        )

        if barycentric_epsilon < 0.0:
            raise ValueError(
                (
                    "barycentric_epsilon "
                    "cannot be negative."
                )
            )

        degenerate_epsilon = (
            _finite_float(
                self.degenerate_uv_epsilon,
                name=(
                    "degenerate_uv_epsilon"
                ),
            )
        )

        if degenerate_epsilon <= 0.0:
            raise ValueError(
                (
                    "degenerate_uv_epsilon "
                    "must be greater than zero."
                )
            )

        _rgba(
            self.background_color,
            name="background_color",
            clamp=(
                self.clamp_colors
            ),
        )


# =========================================================
# Texture buffer
# =========================================================
