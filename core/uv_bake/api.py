from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias

from .constants import *
from .geometry import _MutableBakeStats
from .models import *
from .padding import _dilate_texture
from .primitives import (
    clamp01, _finite_float, _vector2, _vector3, _rgba, _length3, _normalize3,
    _cross3, _subtract3, _interpolate3,
)
from .rasterizer import _rasterize_triangle
from .texture import *

def bake_uv_texture(
    triangles: Iterable[
        UVBakeTriangle
    ],
    sampler: SurfaceColorSampler,
    *,
    config: UVBakeConfig | None = None,
    progress_callback: (
        UVBakeProgressCallback
        | None
    ) = None,
) -> UVBakeResult:
    """
    Rasterize a UV mesh and evaluate one surface color
    function for every covered texture sample.

    Architecture:

        Blender mesh
            ↓ adapter
        UVBakeTriangle[]
            ↓
        core/uv_bake.py
            ↓
        position + normal
            ↓ sampler
        projected color / other appearance implementation
            ↓
        RGBA
            ↓
        rasterized texture
            ↓
        seam padding
            ↓
        UVBakeResult

    The core does NOT:

        - unwrap UVs;
        - know Blender;
        - create Blender images;
        - create materials;
        - save PNG files;
        - know visual hulls;
        - know projected material internals.

    Those responsibilities belong to implementations/.
    """

    if config is None:
        config = (
            UVBakeConfig()
        )

    config.validate()

    if not callable(
        sampler
    ):
        raise TypeError(
            "sampler must be callable."
        )

    if (
        progress_callback
        is not None
        and not callable(
            progress_callback
        )
    ):
        raise TypeError(
            (
                "progress_callback "
                "must be callable."
            )
        )

    triangle_list = tuple(
        triangles
    )

    if not triangle_list:
        raise ValueError(
            (
                "UV bake requires at least "
                "one triangle."
            )
        )

    for (
        index,
        triangle,
    ) in enumerate(
        triangle_list
    ):
        if not isinstance(
            triangle,
            UVBakeTriangle,
        ):
            raise TypeError(
                (
                    "triangles must contain "
                    "UVBakeTriangle values. "
                    f"Item {index} is "
                    f"{type(triangle).__name__}."
                )
            )

    background = (
        _rgba(
            config.background_color,
            name="background_color",
            clamp=(
                config.clamp_colors
            ),
        )
    )

    texture = (
        TextureBuffer.filled(
            config.width,
            config.height,
            background,
        )
    )

    pixel_count = (
        texture.pixel_count
    )

    coverage = bytearray(
        pixel_count
    )

    overlap_mask = bytearray(
        pixel_count
    )

    ownership_scores = (
        array(
            "f",
            [
                -1.0
            ],
        )
        * pixel_count
    )

    mutable_stats = (
        _MutableBakeStats()
    )

    total_triangles = len(
        triangle_list
    )

    for (
        triangle_index,
        triangle,
    ) in enumerate(
        triangle_list
    ):
        rasterized = (
            _rasterize_triangle(
                triangle,
                texture=texture,
                coverage=coverage,
                ownership_scores=(
                    ownership_scores
                ),
                overlap_mask=(
                    overlap_mask
                ),
                sampler=sampler,
                config=config,
                stats=(
                    mutable_stats
                ),
            )
        )

        if rasterized:
            mutable_stats.rasterized_triangles += 1

        if progress_callback is not None:
            progress_callback(
                UVBakeProgress(
                    completed_triangles=(
                        triangle_index
                        + 1
                    ),
                    total_triangles=(
                        total_triangles
                    ),
                )
            )

    covered_pixels = sum(
        coverage
    )

    (
        filled,
        padded_pixels,
    ) = (
        _dilate_texture(
            texture,
            coverage,
            padding_pixels=(
                config
                .padding_pixels
            ),
        )
    )

    stats = (
        UVBakeStats(
            triangle_count=(
                total_triangles
            ),
            rasterized_triangles=(
                mutable_stats
                .rasterized_triangles
            ),
            degenerate_triangles=(
                mutable_stats
                .degenerate_triangles
            ),
            clipped_triangles=(
                mutable_stats
                .clipped_triangles
            ),
            outside_triangles=(
                mutable_stats
                .outside_triangles
            ),
            covered_pixels=int(
                covered_pixels
            ),
            padded_pixels=(
                padded_pixels
            ),
            overlap_pixels=(
                mutable_stats
                .overlap_pixels
            ),
            surface_samples=(
                mutable_stats
                .surface_samples
            ),
            fallback_samples=(
                mutable_stats
                .fallback_samples
            ),
            selected_source_samples=(
                mutable_stats
                .selected_source_samples
            ),
            texture_width=(
                config.width
            ),
            texture_height=(
                config.height
            ),
            samples_per_axis=(
                config
                .samples_per_axis
            ),
            padding_pixels=(
                config
                .padding_pixels
            ),
        )
    )

    return (
        UVBakeResult(
            texture=texture,
            stats=stats,
            coverage=bytes(
                coverage
            ),
            filled=filled,
        )
    )


# =========================================================
# Convenience helpers
# =========================================================

def square_texture_config(
    size: int,
    *,
    padding_pixels: int = (
        DEFAULT_PADDING_PIXELS
    ),
    samples_per_axis: int = (
        DEFAULT_SAMPLES_PER_AXIS
    ),
    background_color: RGBA = (
        DEFAULT_BACKGROUND_COLOR
    ),
    clamp_colors: bool = True,
) -> UVBakeConfig:
    """
    Convenience constructor for the usual square texture
    workflow.
    """

    return UVBakeConfig(
        width=int(
            size
        ),
        height=int(
            size
        ),
        padding_pixels=int(
            padding_pixels
        ),
        samples_per_axis=int(
            samples_per_axis
        ),
        background_color=(
            background_color
        ),
        clamp_colors=bool(
            clamp_colors
        ),
    )


def texture_memory_bytes(
    width: int,
    height: int,
) -> int:
    """
    Approximate memory occupied by the RGBA float texture
    buffer itself.

    Does not include Python object overhead, coverage masks or
    temporary raster state.
    """

    normalized_width = int(
        width
    )

    normalized_height = int(
        height
    )

    if (
        normalized_width < 0
        or normalized_height < 0
    ):
        raise ValueError(
            (
                "Texture dimensions "
                "cannot be negative."
            )
        )

    return (
        normalized_width
        * normalized_height
        * COLOR_CHANNEL_COUNT
        * 4
    )
