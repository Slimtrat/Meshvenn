from __future__ import annotations

import math
from dataclasses import dataclass, field

from .masks import BinaryMask, normalize_mask


Bounds3D = tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class VoxelVolume:
    width: int
    depth: int
    height: int
    values: bytes
    occupied_bounds: Bounds3D | None = None
    _occupied_count: int | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("Volume width must be greater than zero.")
        if self.depth <= 0:
            raise ValueError("Volume depth must be greater than zero.")
        if self.height <= 0:
            raise ValueError("Volume height must be greater than zero.")

        expected_size = self.width * self.depth * self.height
        raw = self.values

        if not isinstance(raw, bytes):
            raw = bytes(1 if value else 0 for value in raw)
            object.__setattr__(self, "values", raw)

        if len(raw) != expected_size:
            raise ValueError(
                f"Volume contains {len(raw)} voxels, expected {expected_size}."
            )

    def index(self, x: int, y: int, z: int) -> int:
        return z * self.depth * self.width + y * self.width + x

    def get(self, x: int, y: int, z: int) -> bool:
        if (
            x < 0 or x >= self.width
            or y < 0 or y >= self.depth
            or z < 0 or z >= self.height
        ):
            return False
        return bool(self.values[self.index(x, y, z)])

    @property
    def occupied_count(self) -> int:
        if self._occupied_count is not None:
            return self._occupied_count
        return sum(self.values)

    @property
    def occupancy_ratio(self) -> float:
        total = self.width * self.depth * self.height
        return self.occupied_count / total if total else 0.0


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


@dataclass(frozen=True)
class CompiledProjection:
    mask_values: bytes
    mask_width: int
    mask_height: int
    cos_az: float
    sin_az: float
    cos_el: float
    sin_el: float
    horizontal_extent: float
    vertical_extent: float
    name: str = ""


class VisualHullSession:
    """Incremental visual-hull builder.

    A session starts with the full voxel cube alive. Each projection only
    evaluates voxels that survived previous projections. Snapshots can be
    taken after L2/L4/L8/L10 without recomputing earlier views.
    """

    def __init__(
        self,
        *,
        options: VisualHullOptions | None = None,
    ) -> None:
        self.options = options or VisualHullOptions()
        _validate_options(self.options)

        self.resolution = self.options.resolution
        self.width = self.resolution
        self.depth = self.resolution
        self.height = self.resolution

        total = self.resolution ** 3
        self._values = bytearray(b"\x01") * total
        self._alive_indices = list(range(total))
        self._applied_count = 0

        self._coords = tuple(
            _grid_to_normalized(index, self.resolution)
            for index in range(self.resolution)
        )

        self._bounds: Bounds3D | None = (
            0,
            self.width - 1,
            0,
            self.depth - 1,
            0,
            self.height - 1,
        )

    @property
    def alive_count(self) -> int:
        return len(self._alive_indices)

    @property
    def applied_count(self) -> int:
        return self._applied_count

    def apply_view(self, projection: ProjectionView, *, name: str = "") -> int:
        if not projection.enabled:
            return self.alive_count

        compiled = compile_projection(
            projection,
            self.resolution,
            name=name,
        )
        self.apply_compiled(compiled)
        return self.alive_count

    def apply_compiled(self, projection: CompiledProjection) -> int:
        if not self._alive_indices:
            self._applied_count += 1
            self._bounds = None
            return 0

        width = self.width
        depth = self.depth
        plane = width * depth
        coords = self._coords

        mask = projection.mask_values
        mask_width = projection.mask_width
        mask_height = projection.mask_height

        cos_az = projection.cos_az
        sin_az = projection.sin_az
        cos_el = projection.cos_el
        sin_el = projection.sin_el
        horizontal_extent = projection.horizontal_extent
        vertical_extent = projection.vertical_extent

        next_alive: list[int] = []
        append_alive = next_alive.append
        values = self._values

        min_x = width
        min_y = depth
        min_z = self.height
        max_x = -1
        max_y = -1
        max_z = -1

        for index in self._alive_indices:
            z, remainder = divmod(index, plane)
            y, x = divmod(remainder, width)

            nx = coords[x]
            ny = coords[y]
            nz = coords[z]

            # Rotate by -azimuth.
            x1 = nx * cos_az - ny * sin_az
            y1 = nx * sin_az + ny * cos_az

            # Elevation affects vertical camera coordinate.
            z2 = y1 * sin_el + nz * cos_el

            normalized_u = x1 / horizontal_extent
            normalized_v = z2 / vertical_extent

            u = (normalized_u + 1.0) * 0.5
            v = (normalized_v + 1.0) * 0.5

            if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
                values[index] = 0
                continue

            mask_x = min(
                int(u * (mask_width - 1) + 0.5),
                mask_width - 1,
            )
            mask_y = min(
                int(v * (mask_height - 1) + 0.5),
                mask_height - 1,
            )

            if not mask[mask_y * mask_width + mask_x]:
                values[index] = 0
                continue

            append_alive(index)

            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
            if z < min_z:
                min_z = z
            if z > max_z:
                max_z = z

        self._alive_indices = next_alive
        self._applied_count += 1

        if max_x < 0:
            self._bounds = None
        else:
            self._bounds = (
                min_x,
                max_x,
                min_y,
                max_y,
                min_z,
                max_z,
            )

        return len(next_alive)

    def snapshot(self) -> VoxelVolume:
        volume = VoxelVolume(
            width=self.width,
            depth=self.depth,
            height=self.height,
            values=bytes(self._values),
            occupied_bounds=self._bounds,
            _occupied_count=len(self._alive_indices),
        )

        if self.options.symmetry_x:
            return enforce_volume_symmetry_x(volume)

        return volume


def compile_projection(
    projection: ProjectionView,
    resolution: int,
    *,
    name: str = "",
) -> CompiledProjection:
    normalized = _normalize_projection_view(projection, resolution)

    azimuth = math.radians(normalized.azimuth_degrees)
    elevation = math.radians(normalized.elevation_degrees)

    cos_az_abs = abs(math.cos(azimuth))
    sin_az_abs = abs(math.sin(azimuth))
    horizontal_extent = max(cos_az_abs + sin_az_abs, 1e-9)

    cos_el_abs = abs(math.cos(elevation))
    sin_el_abs = abs(math.sin(elevation))
    vertical_extent = max(
        horizontal_extent * sin_el_abs + cos_el_abs,
        1e-9,
    )

    # Store rotation by negative angles directly.
    return CompiledProjection(
        mask_values=normalized.mask.values,
        mask_width=normalized.mask.width,
        mask_height=normalized.mask.height,
        cos_az=math.cos(-azimuth),
        sin_az=math.sin(-azimuth),
        cos_el=math.cos(-elevation),
        sin_el=math.sin(-elevation),
        horizontal_extent=horizontal_extent,
        vertical_extent=vertical_extent,
        name=name,
    )


def build_visual_hull(
    projections: list[ProjectionView],
    *,
    options: VisualHullOptions | None = None,
) -> VoxelVolume:
    options = options or VisualHullOptions()
    active = [projection for projection in projections if projection.enabled]

    if len(active) < 2:
        raise ValueError("At least two enabled projections are required.")

    session = VisualHullSession(options=options)
    for projection in active:
        session.apply_view(projection)

    return session.snapshot()


def find_occupied_bounds(
    volume: VoxelVolume,
) -> Bounds3D | None:
    if volume.occupied_bounds is not None:
        return volume.occupied_bounds

    width = volume.width
    depth = volume.depth
    plane = width * depth

    min_x = width
    min_y = depth
    min_z = volume.height
    max_x = -1
    max_y = -1
    max_z = -1

    for index, occupied in enumerate(volume.values):
        if not occupied:
            continue

        z, remainder = divmod(index, plane)
        y, x = divmod(remainder, width)

        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y
        if z < min_z:
            min_z = z
        if z > max_z:
            max_z = z

    if max_x < 0:
        return None

    return min_x, max_x, min_y, max_y, min_z, max_z


def crop_empty_bounds(volume: VoxelVolume) -> VoxelVolume:
    bounds = find_occupied_bounds(volume)
    if bounds is None:
        return volume

    min_x, max_x, min_y, max_y, min_z, max_z = bounds
    new_width = max_x - min_x + 1
    new_depth = max_y - min_y + 1
    new_height = max_z - min_z + 1

    result = bytearray(new_width * new_depth * new_height)
    target = 0
    source = volume.values
    source_width = volume.width
    source_depth = volume.depth
    source_plane = source_width * source_depth

    for z in range(min_z, max_z + 1):
        z_start = z * source_plane
        for y in range(min_y, max_y + 1):
            source_start = z_start + y * source_width + min_x
            row = source[source_start:source_start + new_width]
            result[target:target + new_width] = row
            target += new_width

    return VoxelVolume(
        width=new_width,
        depth=new_depth,
        height=new_height,
        values=bytes(result),
        occupied_bounds=(
            0,
            new_width - 1,
            0,
            new_depth - 1,
            0,
            new_height - 1,
        ),
        _occupied_count=volume.occupied_count,
    )


def enforce_volume_symmetry_x(volume: VoxelVolume) -> VoxelVolume:
    width = volume.width
    depth = volume.depth
    values = bytearray(volume.values)
    half_width = (width + 1) // 2
    occupied_count = 0

    min_x = width
    min_y = depth
    min_z = volume.height
    max_x = -1
    max_y = -1
    max_z = -1

    for z in range(volume.height):
        z_start = z * depth * width
        for y in range(depth):
            row = z_start + y * width

            for x in range(half_width):
                opposite_x = width - 1 - x
                occupied = values[row + x] or values[row + opposite_x]
                values[row + x] = occupied
                values[row + opposite_x] = occupied

            row_values = values[row:row + width]
            row_count = sum(row_values)
            if row_count:
                occupied_count += row_count
                first = row_values.find(b"\x01")
                last = row_values.rfind(b"\x01")
                if first < min_x:
                    min_x = first
                if last > max_x:
                    max_x = last
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
                if z < min_z:
                    min_z = z
                if z > max_z:
                    max_z = z

    bounds = None
    if max_x >= 0:
        bounds = (min_x, max_x, min_y, max_y, min_z, max_z)

    return VoxelVolume(
        width=volume.width,
        depth=volume.depth,
        height=volume.height,
        values=bytes(values),
        occupied_bounds=bounds,
        _occupied_count=occupied_count,
    )


def _grid_to_normalized(value: int, size: int) -> float:
    if size <= 1:
        return 0.0
    return (value / (size - 1)) * 2.0 - 1.0


def _normalize_projection_view(
    projection: ProjectionView,
    resolution: int,
) -> ProjectionView:
    mask = projection.mask

    if projection.flip_x:
        mask = mask.flipped_x()

    normalized_mask = normalize_mask(
        mask,
        resolution,
        resolution,
        crop_content=False,
    )

    return ProjectionView(
        mask=normalized_mask,
        azimuth_degrees=projection.azimuth_degrees,
        elevation_degrees=projection.elevation_degrees,
        flip_x=False,
        enabled=projection.enabled,
    )


def _validate_options(options: VisualHullOptions) -> None:
    if options.resolution < 8:
        raise ValueError("Resolution must be at least 8.")
    if options.resolution > 256:
        raise ValueError("Resolution must not exceed 256.")
