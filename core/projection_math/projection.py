from __future__ import annotations

import math

from .coordinates import surface_position_to_normalized
from .models import EPSILON, NormalizedPoint, ProjectedPoint, ProjectionTransform


def compile_projection(
    *, azimuth_degrees: float, elevation_degrees: float, flip_x: bool = False
) -> ProjectionTransform:
    """Compile the transform used by the native visual-hull engine."""

    azimuth = math.radians(float(azimuth_degrees))
    elevation = math.radians(float(elevation_degrees))
    cos_az, sin_az = math.cos(azimuth), math.sin(azimuth)
    cos_el, sin_el = math.cos(elevation), math.sin(elevation)
    horizontal_extent = max(abs(cos_az) + abs(sin_az), EPSILON)
    vertical_extent = max(horizontal_extent * abs(sin_el) + abs(cos_el), EPSILON)
    return ProjectionTransform(
        azimuth_degrees=float(azimuth_degrees),
        elevation_degrees=float(elevation_degrees),
        cos_az=cos_az,
        sin_az=-sin_az,
        cos_el=cos_el,
        sin_el=-sin_el,
        horizontal_extent=horizontal_extent,
        vertical_extent=vertical_extent,
        flip_x=bool(flip_x),
    )


def project_normalized_point(
    point: NormalizedPoint, transform: ProjectionTransform
) -> ProjectedPoint:
    """Project a normalized point into bottom-left-origin image UV space."""

    nx, ny, nz = float(point.x), float(point.y), float(point.z)
    x1 = nx * transform.cos_az - ny * transform.sin_az
    y1 = nx * transform.sin_az + ny * transform.cos_az
    z2 = y1 * transform.sin_el + nz * transform.cos_el
    u = (x1 / transform.horizontal_extent + 1.0) * 0.5
    v = (z2 / transform.vertical_extent + 1.0) * 0.5
    if transform.flip_x:
        u = 1.0 - u
    return ProjectedPoint(u=u, v=v)


def project_surface_position(
    position: tuple[float, float, float],
    *,
    transform: ProjectionTransform,
    width: int,
    depth: int,
    height: int,
    voxel_size: float = 1.0,
    center_xy: bool = True,
) -> ProjectedPoint:
    normalized = surface_position_to_normalized(
        position,
        width=width,
        depth=depth,
        height=height,
        voxel_size=voxel_size,
        center_xy=center_xy,
    )
    return project_normalized_point(normalized, transform)


def direction_to_camera(
    *, azimuth_degrees: float, elevation_degrees: float
) -> tuple[float, float, float]:
    """Return the unit direction from the object toward the camera."""

    azimuth = math.radians(float(azimuth_degrees))
    elevation = math.radians(float(elevation_degrees))
    horizontal = math.cos(elevation)
    return (
        math.sin(azimuth) * horizontal,
        -math.cos(azimuth) * horizontal,
        math.sin(elevation),
    )
