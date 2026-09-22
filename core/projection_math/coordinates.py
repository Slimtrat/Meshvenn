from __future__ import annotations

from .models import NormalizedPoint


def grid_to_normalized(value: float, size: int) -> float:
    """Map native voxel indices from ``[0, size - 1]`` to ``[-1, 1]``."""

    if size <= 1:
        return 0.0
    return (float(value) / float(size - 1)) * 2.0 - 1.0


def surface_position_to_normalized(
    position: tuple[float, float, float],
    *,
    width: int,
    depth: int,
    height: int,
    voxel_size: float = 1.0,
    center_xy: bool = True,
) -> NormalizedPoint:
    """Convert a surface-envelope position to reconstruction coordinates."""

    if width <= 0 or depth <= 0 or height <= 0:
        raise ValueError("Volume dimensions must be greater than zero.")
    if voxel_size <= 0.0:
        raise ValueError("voxel_size must be greater than zero.")

    x, y, z = position
    grid_x = float(x) / voxel_size
    grid_y = float(y) / voxel_size
    if center_xy:
        grid_x += float(width) * 0.5
        grid_y += float(depth) * 0.5

    return NormalizedPoint(
        x=(grid_x / float(width)) * 2.0 - 1.0,
        y=(grid_y / float(depth)) * 2.0 - 1.0,
        z=((float(z) / voxel_size) / float(height)) * 2.0 - 1.0,
    )
