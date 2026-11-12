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


def projection_aligned_axes(transform: ProjectionTransform):
    """Return right/up/to-camera axes from the *native projector's* rows.

    These differ from legacy ``direction_to_camera`` for nonzero elevation.
    Native inverse elevation gives to-camera Z = -sin(elevation), which lies
    in the null space of both projected coordinates. Legacy behavior is kept.
    Flip X reverses image U, not the geometric viewing direction.

    With the compiled coefficients ca=cos(a), sa=-sin(a), ce=cos(e),
    se=-sin(e), the projector rows are R=(ca,-sa,0) and
    U=(sa*se,ca*se,ce). D=R cross U=(-sa*ce,-ca*ce,se).
    R dot D=0 and U dot D=se*ce*(1-ca**2-sa**2)=0. Thus translating
    along D conserves both UV coordinates, including at the poles.
    """
    ca, sa, ce, se = transform.cos_az, transform.sin_az, transform.cos_el, transform.sin_el
    values = (ca, sa, ce, se, transform.horizontal_extent, transform.vertical_extent)
    if not all(math.isfinite(v) for v in values) or min(values[-2:]) <= 0:
        raise ValueError("Projection coefficients must be finite with positive extents.")
    return ((ca, -sa, 0.0), (sa * se, ca * se, ce), (-sa * ce, -ca * ce, se))


def unproject_normalized_uv(u: float, v: float, transform: ProjectionTransform,
                            *, depth: float = 0.0) -> NormalizedPoint:
    """Invert projected UV at a declared signed to-camera depth.

    Original source-image registration must be mapped with ``aligned_uv``
    before this function; ``u`` already includes the camera's Flip X.
    """
    if not all(math.isfinite(value) for value in (u, v, depth)):
        raise ValueError("Projection coordinates and depth must be finite.")
    right, up, to_camera = projection_aligned_axes(transform)
    horizontal = ((1.0 - u if transform.flip_x else u) * 2 - 1) * transform.horizontal_extent
    vertical = (v * 2 - 1) * transform.vertical_extent
    return NormalizedPoint(*(horizontal * right[i] + vertical * up[i] + depth * to_camera[i]
                             for i in range(3)))
