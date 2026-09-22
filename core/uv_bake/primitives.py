from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias

from .constants import *

def clamp01(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            1.0,
            float(
                value
            ),
        ),
    )


def _finite_float(
    value: Any,
    *,
    name: str,
) -> float:
    result = float(
        value
    )

    if not math.isfinite(
        result
    ):
        raise ValueError(
            f"{name} must be finite."
        )

    return result


def _vector2(
    value: Sequence[
        float
    ],
    *,
    name: str,
) -> Vector2:
    if len(value) != 2:
        raise ValueError(
            (
                f"{name} must contain "
                "exactly 2 values."
            )
        )

    return (
        _finite_float(
            value[0],
            name=f"{name}.x",
        ),
        _finite_float(
            value[1],
            name=f"{name}.y",
        ),
    )


def _vector3(
    value: Sequence[
        float
    ],
    *,
    name: str,
) -> Vector3:
    if len(value) != 3:
        raise ValueError(
            (
                f"{name} must contain "
                "exactly 3 values."
            )
        )

    return (
        _finite_float(
            value[0],
            name=f"{name}.x",
        ),
        _finite_float(
            value[1],
            name=f"{name}.y",
        ),
        _finite_float(
            value[2],
            name=f"{name}.z",
        ),
    )


def _rgba(
    value: Sequence[
        float
    ],
    *,
    name: str,
    clamp: bool,
) -> RGBA:
    if len(value) != 4:
        raise ValueError(
            (
                f"{name} must contain "
                "exactly 4 values."
            )
        )

    channels = tuple(
        _finite_float(
            channel,
            name=(
                f"{name}[{index}]"
            ),
        )
        for (
            index,
            channel,
        ) in enumerate(
            value
        )
    )

    if clamp:
        return (
            clamp01(
                channels[0]
            ),
            clamp01(
                channels[1]
            ),
            clamp01(
                channels[2]
            ),
            clamp01(
                channels[3]
            ),
        )

    return (
        channels[0],
        channels[1],
        channels[2],
        channels[3],
    )


# =========================================================
# Vector math
# =========================================================

def _length3(
    value: Vector3,
) -> float:
    return math.sqrt(
        value[0]
        * value[0]
        + value[1]
        * value[1]
        + value[2]
        * value[2]
    )


def _normalize3(
    value: Vector3,
) -> Vector3:
    length = _length3(
        value
    )

    if (
        not math.isfinite(
            length
        )
        or length
        <= NORMAL_EPSILON
    ):
        raise ValueError(
            (
                "Surface normal must be "
                "a finite non-zero vector."
            )
        )

    inverse = (
        1.0
        / length
    )

    return (
        value[0]
        * inverse,
        value[1]
        * inverse,
        value[2]
        * inverse,
    )


def _cross3(
    a: Vector3,
    b: Vector3,
) -> Vector3:
    return (
        a[1] * b[2]
        - a[2] * b[1],

        a[2] * b[0]
        - a[0] * b[2],

        a[0] * b[1]
        - a[1] * b[0],
    )


def _subtract3(
    a: Vector3,
    b: Vector3,
) -> Vector3:
    return (
        a[0] - b[0],
        a[1] - b[1],
        a[2] - b[2],
    )


def _interpolate3(
    a: Vector3,
    b: Vector3,
    c: Vector3,
    weights: tuple[
        float,
        float,
        float,
    ],
) -> Vector3:
    (
        wa,
        wb,
        wc,
    ) = weights

    return (
        a[0] * wa
        + b[0] * wb
        + c[0] * wc,

        a[1] * wa
        + b[1] * wb
        + c[1] * wc,

        a[2] * wa
        + b[2] * wb
        + c[2] * wc,
    )


# =========================================================
# Bake vertex
# =========================================================
