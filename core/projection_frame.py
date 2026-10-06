"""Physical camera spans matching the native normalized-cube projection."""
from __future__ import annotations

import math


def native_projection_axes(azimuth: float, elevation: float):
    """Camera right, up and backward basis; includes stable pole orientation."""
    if not all(math.isfinite(v) for v in (azimuth, elevation)):
        raise ValueError("Projection angles must be finite.")
    az, el = math.radians(azimuth), math.radians(elevation)
    ca, sa, ce, se = math.cos(az), math.sin(az), math.cos(el), math.sin(el)
    return ((ca, sa, 0.), (sa*se, -ca*se, ce), (sa*ce, -ca*ce, -se))


def native_projection_frame(side: float, azimuth: float, elevation: float,
                            width: int, height: int) -> tuple[float, float]:
    """Return Blender ortho scale and pixel aspect X (aspect Y stays one).

    The native scanner divides by the projected extent of a cube, not by
    a common orthographic image height. Rectangular sheet cells therefore
    need both angle-dependent spans and non-square render pixels.
    """
    if (not all(math.isfinite(v) for v in (side, azimuth, elevation))
            or side <= 0 or width <= 0 or height <= 0):
        raise ValueError("Projection frame requires finite angles and positive dimensions.")
    az, el = math.radians(azimuth), math.radians(elevation)
    horizontal = max(abs(math.cos(az)) + abs(math.sin(az)), 1e-9)
    vertical = max(horizontal * abs(math.sin(el)) + abs(math.cos(el)), 1e-9)
    return side * max(horizontal, vertical), (horizontal / vertical) * height / width
