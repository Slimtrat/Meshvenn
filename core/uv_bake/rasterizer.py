from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias

from .constants import *
from .geometry import (
    _MutableBakeStats, _coerce_surface_sample, _barycentric_weights, _interior_score,
    _face_normal, _surface_point, _triangle_pixel_bounds,
)
from .models import *
from .primitives import (
    clamp01, _finite_float, _vector2, _vector3, _rgba, _length3, _normalize3,
    _cross3, _subtract3, _interpolate3,
)
from .texture import *

def _subsample_offsets(
    samples_per_axis: int,
) -> tuple[
    float,
    ...
]:
    inverse = (
        1.0
        / float(
            samples_per_axis
        )
    )

    return tuple(
        (
            float(
                index
            )
            + 0.5
        )
        * inverse
        for index
        in range(
            samples_per_axis
        )
    )


# =========================================================
# Triangle rasterization
# =========================================================

def _rasterize_triangle(
    triangle: UVBakeTriangle,
    *,
    texture: TextureBuffer,
    coverage: bytearray,
    ownership_scores: array,
    overlap_mask: bytearray,
    sampler: SurfaceColorSampler,
    config: UVBakeConfig,
    stats: _MutableBakeStats,
) -> bool:
    if (
        abs(
            triangle
            .signed_uv_area_twice
        )
        <= config
        .degenerate_uv_epsilon
    ):
        stats.degenerate_triangles += 1

        return False

    if (
        triangle
        .has_uv_outside_unit_square
    ):
        stats.clipped_triangles += 1

    bounds = (
        _triangle_pixel_bounds(
            triangle,
            width=(
                texture.width
            ),
            height=(
                texture.height
            ),
        )
    )

    if bounds is None:
        stats.outside_triangles += 1

        return False

    (
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
    ) = bounds

    offsets = (
        _subsample_offsets(
            config.samples_per_axis
        )
    )

    triangle_wrote_pixel = False

    for y in range(
        minimum_y,
        maximum_y + 1,
    ):
        for x in range(
            minimum_x,
            maximum_x + 1,
        ):
            accumulated_red = 0.0

            accumulated_green = 0.0

            accumulated_blue = 0.0

            accumulated_alpha = 0.0

            accumulated_score = 0.0

            sample_count = 0

            fallback_count = 0

            selected_source_samples = 0

            for offset_y in (
                offsets
            ):
                v = (
                    (
                        float(
                            y
                        )
                        + offset_y
                    )
                    / float(
                        texture.height
                    )
                )

                for offset_x in (
                    offsets
                ):
                    u = (
                        (
                            float(
                                x
                            )
                            + offset_x
                        )
                        / float(
                            texture.width
                        )
                    )

                    weights = (
                        _barycentric_weights(
                            (
                                u,
                                v,
                            ),
                            triangle,
                            epsilon=(
                                config
                                .barycentric_epsilon
                            ),
                        )
                    )

                    if weights is None:
                        continue

                    (
                        position,
                        normal,
                    ) = (
                        _surface_point(
                            triangle,
                            weights,
                        )
                    )

                    sampled = (
                        _coerce_surface_sample(
                            sampler(
                                position,
                                normal,
                            ),
                            clamp_colors=(
                                config
                                .clamp_colors
                            ),
                        )
                    )

                    (
                        red,
                        green,
                        blue,
                        alpha,
                    ) = (
                        sampled.color
                    )

                    accumulated_red += (
                        red
                    )

                    accumulated_green += (
                        green
                    )

                    accumulated_blue += (
                        blue
                    )

                    accumulated_alpha += (
                        alpha
                    )

                    accumulated_score += (
                        _interior_score(
                            weights
                        )
                    )

                    sample_count += 1

                    if sampled.used_fallback:
                        fallback_count += 1

                    selected_source_samples += (
                        sampled
                        .selected_samples
                    )

            if sample_count == 0:
                continue

            inverse_sample_count = (
                1.0
                / float(
                    sample_count
                )
            )

            color = (
                accumulated_red
                * inverse_sample_count,

                accumulated_green
                * inverse_sample_count,

                accumulated_blue
                * inverse_sample_count,

                accumulated_alpha
                * inverse_sample_count,
            )

            score = (
                accumulated_score
                * inverse_sample_count
            )

            pixel_index = (
                y
                * texture.width
                + x
            )

            already_covered = bool(
                coverage[
                    pixel_index
                ]
            )

            if (
                already_covered
                and not overlap_mask[
                    pixel_index
                ]
            ):
                overlap_mask[
                    pixel_index
                ] = 1

                stats.overlap_pixels += 1

            # -------------------------------------------------
            # Resolve UV overlap.
            #
            # Prefer the triangle whose successful samples lie
            # further inside its UV area.
            #
            # Exact ties preserve the first triangle, keeping
            # output deterministic.
            # -------------------------------------------------

            previous_score = float(
                ownership_scores[
                    pixel_index
                ]
            )

            should_write = (
                not already_covered
                or score
                > previous_score
            )

            if should_write:
                texture.set_rgba(
                    x,
                    y,
                    color,
                )

                ownership_scores[
                    pixel_index
                ] = float(
                    score
                )

                coverage[
                    pixel_index
                ] = 1

                triangle_wrote_pixel = True

            # -------------------------------------------------
            # Sampling diagnostics describe actual work, even
            # when an overlapping triangle loses ownership.
            # -------------------------------------------------

            stats.surface_samples += (
                sample_count
            )

            stats.fallback_samples += (
                fallback_count
            )

            stats.selected_source_samples += (
                selected_source_samples
            )

    return (
        triangle_wrote_pixel
    )


# =========================================================
# Texture padding / dilation
# =========================================================
