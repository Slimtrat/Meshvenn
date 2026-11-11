"""Bounded orthographic silhouettes of native occupied voxel cells.

The native sampler tests centres at i/(size-1), *not* the mesh's surface
envelope. A centre represents its clipped Voronoi cell in that grid. We project
the cell's convex footprint and mark every nearest-neighbour raster cell with
positive overlap. This deliberately conservative silhouette is neither a point
cloud nor a rendering of hidden surfaces, and cannot certify unseen geometry.
"""

from __future__ import annotations

import math
import time
from itertools import product
from typing import Callable

from ..diagnostic_contracts import CameraDeclaration
from ..image_mask import BinaryMask
from ..native_bridge.models import NativeVolume
from ..projection_alignment import ProjectionAlignment
from ..projection_math import (NormalizedPoint, ProjectedPoint,
                               grid_to_normalized, project_normalized_point)

MAX_RASTER_SIDE = 256
MAX_VOLUME_SIDE = 256
DEFAULT_MAX_WORK = 8_000_000
_EPSILON = 1e-9


def _raster_size(width: int, height: int) -> None:
    if any(type(size) is not int or not 1 <= size <= MAX_RASTER_SIDE
           for size in (width, height)):
        raise ValueError(f"Diagnostic raster dimensions must be integers in [1, {MAX_RASTER_SIDE}].")


def aligned_mask(source: BinaryMask, alignment: ProjectionAlignment) -> BinaryMask:
    """Reuse the production registration and native nearest-mask convention."""
    # Original decoded masks drive native carving. Only *measurement* rasters
    # use the smaller 256-axis limit; registration must retain original detail.
    if source.width * source.height > 1_048_576:
        raise ValueError("Original diagnostic masks exceed the 1 Mi-pixel input budget.")
    return alignment.align_mask(source)


def _transform(camera: CameraDeclaration):
    # The property compiles with the shared compile_projection authority.
    transform = camera.transform
    if not all(math.isfinite(value) for value in
               (camera.azimuth_degrees, camera.elevation_degrees)):
        raise ValueError("Diagnostic camera angles must be finite.")
    return transform


def check_budget(deadline: float | None, cancel: Callable[[], bool] | None) -> None:
    """Cooperative checks shared by projection and raster metrics."""
    if deadline is not None and not math.isfinite(deadline):
        raise ValueError("Diagnostic deadline must be finite.")
    if cancel is not None and cancel():
        raise InterruptedError("Geometry diagnostics were cancelled.")
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError("Geometry diagnostic deadline exceeded.")


def _dimensions(volume: NativeVolume) -> tuple[int, int, int]:
    dimensions = (volume.width, volume.depth, volume.height)
    if any(type(size) is not int or not 1 <= size <= MAX_VOLUME_SIDE for size in dimensions):
        raise ValueError(f"Native dimensions must be integers in [1, {MAX_VOLUME_SIDE}].")
    return dimensions


def project_voxel_center(volume: NativeVolume, camera: CameraDeclaration,
                         x: int, y: int, z: int) -> ProjectedPoint:
    """Expose the exact native centre convention for numerical verification."""
    for index, size in zip((x, y, z), _dimensions(volume)):
        if type(index) is not int or not 0 <= index < size:
            raise ValueError("Voxel indices must lie inside the native volume.")
    return project_normalized_point(NormalizedPoint(
        grid_to_normalized(x, volume.width), grid_to_normalized(y, volume.depth),
        grid_to_normalized(z, volume.height)), _transform(camera))


def nearest_mask_pixel(point: ProjectedPoint, *, width: int,
                       height: int) -> tuple[int, int] | None:
    """Native sample_projection: reject outside UVs, round half upward."""
    _raster_size(width, height)
    if not (math.isfinite(point.u) and math.isfinite(point.v)):
        raise ValueError("Projected coordinates must be finite.")
    if not point.inside:
        return None
    return (min(width - 1, int(point.u * (width - 1) + 0.5)),
            min(height - 1, int(point.v * (height - 1) + 0.5)))


def _cell_limits(start: int, end: int, size: int) -> tuple[float, float]:
    if size == 1:
        return (-1.0, 1.0)
    return (max(-1.0, grid_to_normalized(start - 0.5, size)),
            min(1.0, grid_to_normalized(end + 0.5, size)))


def projection_tolerance_pixels(volume: NativeVolume, camera: CameraDeclaration,
                                width: int, height: int) -> float:
    """Maximum projected half-cell displacement plus half a raster diagonal.

    This is a resolution uncertainty bound, not permission to declare a small
    missing component correct. Callers must retain unresolved region checks.
    """
    _raster_size(width, height)
    transform = _transform(camera)
    half_steps = tuple(1.0 / (size - 1) if size > 1 else 1.0
                       for size in _dimensions(volume))
    origin = project_normalized_point(NormalizedPoint(0, 0, 0), transform)
    radius = max(math.hypot((p.u - origin.u) * (width - 1),
                            (p.v - origin.v) * (height - 1))
                 for signs in product((-1, 1), repeat=3)
                 for p in (project_normalized_point(NormalizedPoint(
                     *(sign * step for sign, step in zip(signs, half_steps))), transform),))
    return radius + math.hypot(0.5 if width > 1 else 0,
                               0.5 if height > 1 else 0)


def _convex_hull(points):
    points = sorted(set(points))
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    def half(sequence):
        result = []
        for point in sequence:
            while len(result) >= 2 and cross(result[-2], result[-1], point) <= _EPSILON:
                result.pop()
            result.append(point)
        return result
    return half(points)[:-1] + half(reversed(points))[:-1] if len(points) > 1 else points


def _fill_footprint(values: bytearray, width: int, height: int, hull,
                    rows: range) -> None:
    # Clip the convex polygon to each pixel's horizontal band. Its x projection
    # is an interval; filling that interval is exact for convex cell footprints.
    for y in rows:
        lower, upper = y - 0.5, y + 0.5
        xs = [x for x, py in hull if lower <= py <= upper]
        for index, (ax, ay) in enumerate(hull):
            bx, by = hull[(index + 1) % len(hull)]
            if abs(by - ay) <= _EPSILON:
                continue
            for boundary in (lower, upper):
                if min(ay, by) <= boundary <= max(ay, by):
                    xs.append(ax + (boundary - ay) * (bx - ax) / (by - ay))
        if not xs:
            continue
        left = max(0, math.ceil(min(xs) - 0.5 + _EPSILON))
        right = min(width - 1, math.floor(max(xs) + 0.5 - _EPSILON))
        if left <= right:
            start = y * width + left
            values[start:start + right - left + 1] = b"\x01" * (right - left + 1)


def reproject_volume(volume: NativeVolume, camera: CameraDeclaration, *, width: int,
                     height: int, max_work: int = DEFAULT_MAX_WORK,
                     deadline: float | None = None,
                     cancel: Callable[[], bool] | None = None) -> BinaryMask:
    """Project finite occupied cells with bounded work and no third party code.

    Contiguous X cells merge into exact cuboids before projection. Their union
    is unchanged, including cavities and disconnected parts. Budgets fail
    explicitly; no partial raster is returned as a successful measurement.
    """
    _raster_size(width, height)
    check_budget(deadline, cancel)
    dimensions = _dimensions(volume)
    if type(max_work) is not int or max_work <= 0:
        raise ValueError("Projection work budget must be a positive integer.")
    raw = volume.values
    if not isinstance(raw, bytes) or len(raw) != math.prod(dimensions):
        raise ValueError("Native volume storage does not match its dimensions.")
    occupied = raw.count(1)
    if raw.count(0) + occupied != len(raw) or occupied != volume.occupied_count:
        raise ValueError("Native volume occupancy must be binary and its count consistent.")
    transform = _transform(camera)
    result = bytearray(width * height)
    work = 0
    for z in range(volume.height):
        z_limits = _cell_limits(z, z, volume.height)
        for y in range(volume.depth):
            check_budget(deadline, cancel)
            row = (z * volume.depth + y) * volume.width
            end = row + volume.width
            start = raw.find(b"\x01", row, end)
            while start >= 0:
                stop = raw.find(b"\x00", start, end)
                if stop < 0:
                    stop = end
                limits = (_cell_limits(start - row, stop - row - 1, volume.width),
                          _cell_limits(y, y, volume.depth), z_limits)
                points = [project_normalized_point(NormalizedPoint(*corner), transform)
                          for corner in product(*limits)]
                sx, sy = width - 1, height - 1
                hull = _convex_hull([(p.u * sx, p.v * sy) for p in points])
                low = max(0, math.ceil(min(p[1] for p in hull) - 0.5 + _EPSILON))
                high = min(height - 1, math.floor(max(p[1] for p in hull) + 0.5 - _EPSILON))
                rows = range(low, high + 1)
                work += 8 + len(rows) * len(hull)
                if work > max_work:
                    raise ValueError("Diagnostic projection work budget exceeded.")
                _fill_footprint(result, width, height, hull, rows)
                start = raw.find(b"\x01", stop, end)
    return BinaryMask(width, height, bytes(result))
