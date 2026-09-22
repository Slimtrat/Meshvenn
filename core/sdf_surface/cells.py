from __future__ import annotations

from ..projection_math import grid_to_normalized
from ..sdf import SDFVolume
from .models import SDFSurfaceConfig, SDFSurfaceVertex, Vector3
from .normals import estimate_sdf_normal
from .numeric import (
    append_unique_point,
    average_points,
    edge_crosses_iso,
    edge_interpolation,
    interpolate3,
)


CUBE_CORNERS: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0),
    (1, 0, 0),
    (1, 1, 0),
    (0, 1, 0),
    (0, 0, 1),
    (1, 0, 1),
    (1, 1, 1),
    (0, 1, 1),
)

CUBE_EDGES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
)


def normalized_grid_position(
    volume: SDFVolume, x: int, y: int, z: int
) -> Vector3:
    return (
        grid_to_normalized(x, volume.width),
        grid_to_normalized(y, volume.depth),
        grid_to_normalized(z, volume.height),
    )


def extract_cell_vertex(
    volume: SDFVolume,
    *,
    x: int,
    y: int,
    z: int,
    iso_level: float,
    config: SDFSurfaceConfig,
) -> SDFSurfaceVertex | None:
    corner_values: list[float] = []
    corner_positions: list[Vector3] = []
    for offset_x, offset_y, offset_z in CUBE_CORNERS:
        gx = x + offset_x
        gy = y + offset_y
        gz = z + offset_z
        corner_values.append(volume.get(gx, gy, gz))
        corner_positions.append(normalized_grid_position(volume, gx, gy, gz))

    intersections: list[Vector3] = []
    for first_index, second_index in CUBE_EDGES:
        first_value = corner_values[first_index]
        second_value = corner_values[second_index]
        if not edge_crosses_iso(first_value, second_value, iso_level):
            continue
        factor = edge_interpolation(first_value, second_value, iso_level)
        point = interpolate3(
            corner_positions[first_index], corner_positions[second_index], factor
        )
        append_unique_point(intersections, point)

    if not intersections:
        return None
    position = average_points(intersections)
    normal = (
        estimate_sdf_normal(
            volume, position, step_scale=config.gradient_step_scale
        )
        if config.generate_normals
        else (0.0, 0.0, 0.0)
    )
    return SDFSurfaceVertex(
        position=position,
        normal=normal,
        cell=(x, y, z),
        intersection_count=len(intersections),
    )
