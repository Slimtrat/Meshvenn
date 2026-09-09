# core/visual_hull.py

from __future__ import annotations

import math
from dataclasses import dataclass

from .masks import BinaryMask, resize_mask_nearest


@dataclass(frozen=True)
class VoxelVolume:
    width: int
    depth: int
    height: int
    values: tuple[bool, ...]

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("Volume width must be greater than zero.")

        if self.depth <= 0:
            raise ValueError("Volume depth must be greater than zero.")

        if self.height <= 0:
            raise ValueError("Volume height must be greater than zero.")

        expected_size = self.width * self.depth * self.height

        if len(self.values) != expected_size:
            raise ValueError(
                f"Volume contains {len(self.values)} voxels, "
                f"expected {expected_size}."
            )

    def index(
        self,
        x: int,
        y: int,
        z: int,
    ) -> int:
        return (
            z * self.depth * self.width
            + y * self.width
            + x
        )

    def get(
        self,
        x: int,
        y: int,
        z: int,
    ) -> bool:
        if x < 0 or x >= self.width:
            return False

        if y < 0 or y >= self.depth:
            return False

        if z < 0 or z >= self.height:
            return False

        return self.values[self.index(x, y, z)]

    @property
    def occupied_count(self) -> int:
        return sum(self.values)

    @property
    def occupancy_ratio(self) -> float:
        total = self.width * self.depth * self.height

        if total == 0:
            return 0.0

        return self.occupied_count / total


@dataclass(frozen=True)
class ProjectionView:
    mask: BinaryMask
    azimuth_degrees: float = 0.0
    elevation_degrees: float = 0.0
    flip_x: bool = False
    enabled: bool = True


@dataclass(frozen=True)
class VisualHullOptions:
    resolution: int = 96
    symmetry_x: bool = False


def build_visual_hull(
    projections: list[ProjectionView],
    *,
    options: VisualHullOptions | None = None,
) -> VoxelVolume:
    if options is None:
        options = VisualHullOptions()

    _validate_options(options)

    active_projections = [
        _normalize_projection_view(
            projection,
            options.resolution,
        )
        for projection in projections
        if projection.enabled
    ]

    if len(active_projections) < 2:
        raise ValueError(
            "At least two enabled projections are required."
        )

    width = options.resolution
    depth = options.resolution
    height = options.resolution

    values: list[bool] = []

    for z in range(height):
        for y in range(depth):
            for x in range(width):
                occupied = _voxel_matches_all_projections(
                    x=x,
                    y=y,
                    z=z,
                    width=width,
                    depth=depth,
                    height=height,
                    projections=active_projections,
                )

                values.append(occupied)

    volume = VoxelVolume(
        width=width,
        depth=depth,
        height=height,
        values=tuple(values),
    )

    if options.symmetry_x:
        volume = enforce_volume_symmetry_x(volume)

    return volume


def crop_empty_bounds(
    volume: VoxelVolume,
) -> VoxelVolume:
    bounds = find_occupied_bounds(volume)

    if bounds is None:
        return volume

    (
        min_x,
        max_x,
        min_y,
        max_y,
        min_z,
        max_z,
    ) = bounds

    new_width = max_x - min_x + 1
    new_depth = max_y - min_y + 1
    new_height = max_z - min_z + 1

    values: list[bool] = []

    for z in range(min_z, max_z + 1):
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                values.append(
                    volume.get(x, y, z)
                )

    return VoxelVolume(
        width=new_width,
        depth=new_depth,
        height=new_height,
        values=tuple(values),
    )


def find_occupied_bounds(
    volume: VoxelVolume,
) -> tuple[int, int, int, int, int, int] | None:
    min_x = volume.width
    min_y = volume.depth
    min_z = volume.height

    max_x = -1
    max_y = -1
    max_z = -1

    found = False

    for z in range(volume.height):
        for y in range(volume.depth):
            for x in range(volume.width):
                if not volume.get(x, y, z):
                    continue

                found = True

                min_x = min(min_x, x)
                max_x = max(max_x, x)

                min_y = min(min_y, y)
                max_y = max(max_y, y)

                min_z = min(min_z, z)
                max_z = max(max_z, z)

    if not found:
        return None

    return (
        min_x,
        max_x,
        min_y,
        max_y,
        min_z,
        max_z,
    )


def enforce_volume_symmetry_x(
    volume: VoxelVolume,
) -> VoxelVolume:
    values = list(volume.values)

    half_width = (volume.width + 1) // 2

    for z in range(volume.height):
        for y in range(volume.depth):
            for x in range(half_width):
                opposite_x = volume.width - 1 - x

                occupied = (
                    volume.get(x, y, z)
                    or volume.get(opposite_x, y, z)
                )

                left_index = volume.index(x, y, z)
                right_index = volume.index(opposite_x, y, z)

                values[left_index] = occupied
                values[right_index] = occupied

    return VoxelVolume(
        width=volume.width,
        depth=volume.depth,
        height=volume.height,
        values=tuple(values),
    )


def _voxel_matches_all_projections(
    *,
    x: int,
    y: int,
    z: int,
    width: int,
    depth: int,
    height: int,
    projections: list[ProjectionView],
) -> bool:
    nx = _grid_to_normalized(x, width)
    ny = _grid_to_normalized(y, depth)
    nz = _grid_to_normalized(z, height)

    for projection in projections:
        u, v = _project_voxel_to_mask(
            x=nx,
            y=ny,
            z=nz,
            projection=projection,
        )

        if not _sample_mask_uv(
            projection.mask,
            u,
            v,
        ):
            return False

    return True


def _grid_to_normalized(
    value: int,
    size: int,
) -> float:
    if size <= 1:
        return 0.0

    return (value / (size - 1)) * 2.0 - 1.0


def _project_voxel_to_mask(
    *,
    x: float,
    y: float,
    z: float,
    projection: ProjectionView,
) -> tuple[float, float]:
    azimuth = math.radians(projection.azimuth_degrees)
    elevation = math.radians(projection.elevation_degrees)

    cos_az = math.cos(-azimuth)
    sin_az = math.sin(-azimuth)

    x1 = x * cos_az - y * sin_az
    y1 = x * sin_az + y * cos_az
    z1 = z

    cos_el = math.cos(-elevation)
    sin_el = math.sin(-elevation)

    x2 = x1
    y2 = y1 * cos_el - z1 * sin_el
    z2 = y1 * sin_el + z1 * cos_el

    u = (x2 + 1.0) * 0.5
    v = (z2 + 1.0) * 0.5

    if projection.flip_x:
        u = 1.0 - u

    return u, v


def _sample_mask_uv(
    mask: BinaryMask,
    u: float,
    v: float,
) -> bool:
    if u < 0.0 or u > 1.0:
        return False

    if v < 0.0 or v > 1.0:
        return False

    x = min(
        int(u * (mask.width - 1) + 0.5),
        mask.width - 1,
    )

    y = min(
        int(v * (mask.height - 1) + 0.5),
        mask.height - 1,
    )

    return mask.get(x, y)


def _normalize_projection_view(
    projection: ProjectionView,
    resolution: int,
) -> ProjectionView:
    target_width = resolution
    target_height = resolution

    mask = projection.mask

    if projection.flip_x:
        mask = mask.flipped_x()

    normalized_mask = resize_mask_nearest(
        mask,
        target_width,
        target_height,
    )

    return ProjectionView(
        mask=normalized_mask,
        azimuth_degrees=projection.azimuth_degrees,
        elevation_degrees=projection.elevation_degrees,
        flip_x=False,
        enabled=projection.enabled,
    )


def _validate_options(
    options: VisualHullOptions,
) -> None:
    if options.resolution < 8:
        raise ValueError(
            "Resolution must be at least 8."
        )

    if options.resolution > 256:
        raise ValueError(
            "Resolution must not exceed 256."
        )