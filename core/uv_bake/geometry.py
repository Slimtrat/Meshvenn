from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias

from .constants import *
from .models import *
from .primitives import (
    clamp01, _finite_float, _vector2, _vector3, _rgba, _length3, _normalize3,
    _cross3, _subtract3, _interpolate3,
)

@dataclass
class _MutableBakeStats:
    rasterized_triangles: int = 0

    degenerate_triangles: int = 0

    clipped_triangles: int = 0

    outside_triangles: int = 0

    overlap_pixels: int = 0

    surface_samples: int = 0

    fallback_samples: int = 0

    selected_source_samples: int = 0


# =========================================================
# Surface sample conversion
# =========================================================

def _coerce_surface_sample(
    value: (
        SurfaceColorSample
        | Sequence[
            float
        ]
    ),
    *,
    clamp_colors: bool,
) -> SurfaceColorSample:
    if isinstance(
        value,
        SurfaceColorSample,
    ):
        color = _rgba(
            value.color,
            name="surface sample color",
            clamp=clamp_colors,
        )

        if color == value.color:
            return value

        return SurfaceColorSample(
            color=color,
            used_fallback=(
                value.used_fallback
            ),
            selected_samples=(
                value.selected_samples
            ),
            metadata=(
                value.metadata
            ),
        )

    color = _rgba(
        value,
        name="surface sample",
        clamp=clamp_colors,
    )

    return SurfaceColorSample(
        color=color
    )


# =========================================================
# Barycentric coordinates
# =========================================================

def _barycentric_weights(
    point: Vector2,
    triangle: UVBakeTriangle,
    *,
    epsilon: float,
) -> (
    tuple[
        float,
        float,
        float,
    ]
    | None
):
    (
        px,
        py,
    ) = point

    (
        ax,
        ay,
    ) = (
        triangle.a.uv
    )

    (
        bx,
        by,
    ) = (
        triangle.b.uv
    )

    (
        cx,
        cy,
    ) = (
        triangle.c.uv
    )

    denominator = (
        (
            by - cy
        )
        * (
            ax - cx
        )
        + (
            cx - bx
        )
        * (
            ay - cy
        )
    )

    if (
        not math.isfinite(
            denominator
        )
        or abs(
            denominator
        )
        <= DEFAULT_DEGENERATE_UV_EPSILON
    ):
        return None

    wa = (
        (
            (
                by - cy
            )
            * (
                px - cx
            )
            + (
                cx - bx
            )
            * (
                py - cy
            )
        )
        / denominator
    )

    wb = (
        (
            (
                cy - ay
            )
            * (
                px - cx
            )
            + (
                ax - cx
            )
            * (
                py - cy
            )
        )
        / denominator
    )

    wc = (
        1.0
        - wa
        - wb
    )

    if (
        wa < -epsilon
        or wb < -epsilon
        or wc < -epsilon
    ):
        return None

    return (
        wa,
        wb,
        wc,
    )


def _interior_score(
    weights: tuple[
        float,
        float,
        float,
    ],
) -> float:
    """
    Larger means further inside the triangle.

    This is used when two UV triangles touch/overlap the same
    texel.

    Choosing the most interior candidate is more stable than
    blindly allowing whichever triangle happened to be
    rasterized last.
    """

    return max(
        0.0,
        min(
            weights
        ),
    )


# =========================================================
# Triangle surface interpolation
# =========================================================

def _face_normal(
    triangle: UVBakeTriangle,
) -> Vector3:
    edge_ab = (
        _subtract3(
            triangle.b.position,
            triangle.a.position,
        )
    )

    edge_ac = (
        _subtract3(
            triangle.c.position,
            triangle.a.position,
        )
    )

    return _normalize3(
        _cross3(
            edge_ab,
            edge_ac,
        )
    )


def _surface_point(
    triangle: UVBakeTriangle,
    weights: tuple[
        float,
        float,
        float,
    ],
) -> tuple[
    Vector3,
    Vector3,
]:
    position = (
        _interpolate3(
            triangle.a.position,
            triangle.b.position,
            triangle.c.position,
            weights,
        )
    )

    interpolated_normal = (
        _interpolate3(
            triangle.a.normal,
            triangle.b.normal,
            triangle.c.normal,
            weights,
        )
    )

    try:
        normal = (
            _normalize3(
                interpolated_normal
            )
        )

    except ValueError:
        normal = (
            _face_normal(
                triangle
            )
        )

    return (
        position,
        normal,
    )


# =========================================================
# Pixel-space bounds
# =========================================================

def _triangle_pixel_bounds(
    triangle: UVBakeTriangle,
    *,
    width: int,
    height: int,
) -> (
    tuple[
        int,
        int,
        int,
        int,
    ]
    | None
):
    u_values = (
        triangle.a.uv[0],
        triangle.b.uv[0],
        triangle.c.uv[0],
    )

    v_values = (
        triangle.a.uv[1],
        triangle.b.uv[1],
        triangle.c.uv[1],
    )

    minimum_u = min(
        u_values
    )

    maximum_u = max(
        u_values
    )

    minimum_v = min(
        v_values
    )

    maximum_v = max(
        v_values
    )

    if (
        maximum_u < 0.0
        or minimum_u > 1.0
        or maximum_v < 0.0
        or minimum_v > 1.0
    ):
        return None

    minimum_x = max(
        0,
        int(
            math.floor(
                minimum_u
                * width
            )
        ),
    )

    maximum_x = min(
        width - 1,
        int(
            math.ceil(
                maximum_u
                * width
            )
            - 1
        ),
    )

    minimum_y = max(
        0,
        int(
            math.floor(
                minimum_v
                * height
            )
        ),
    )

    maximum_y = min(
        height - 1,
        int(
            math.ceil(
                maximum_v
                * height
            )
            - 1
        ),
    )

    if (
        minimum_x > maximum_x
        or minimum_y > maximum_y
    ):
        return None

    return (
        minimum_x,
        maximum_x,
        minimum_y,
        maximum_y,
    )


# =========================================================
# Subsample locations
# =========================================================
