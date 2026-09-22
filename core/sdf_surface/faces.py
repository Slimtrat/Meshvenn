from __future__ import annotations

from ..sdf import SDFVolume
from .models import CellCoordinate, Quad
from .numeric import edge_crosses_iso


def oriented_quad(
    base: Quad,
    *,
    lower_value: float,
    upper_value: float,
    iso_level: float,
) -> Quad:
    lower_inside = lower_value <= iso_level
    upper_inside = upper_value <= iso_level
    if lower_inside and not upper_inside:
        return base
    return base[0], base[3], base[2], base[1]


def resolve_quad(
    cells: tuple[
        CellCoordinate, CellCoordinate, CellCoordinate, CellCoordinate
    ],
    cell_vertices: dict[CellCoordinate, int],
) -> Quad | None:
    try:
        return tuple(cell_vertices[cell] for cell in cells)  # type: ignore[return-value]
    except KeyError:
        return None


def build_faces(
    volume: SDFVolume,
    cell_vertices: dict[CellCoordinate, int],
    iso_level: float,
) -> tuple[list[Quad], int, int, int, int, int, int]:
    """Emit one oriented quad for every resolvable sign-changing grid edge."""

    width, depth, height = volume.width, volume.depth, volume.height
    faces: list[Quad] = []
    crossing_grid_edges = 0
    emitted_x_quads = emitted_y_quads = emitted_z_quads = 0
    skipped_boundary_edges = skipped_missing_cell_edges = 0

    def append_for_edge(
        cells: tuple[
            CellCoordinate, CellCoordinate, CellCoordinate, CellCoordinate
        ],
        lower: float,
        upper: float,
    ) -> bool:
        nonlocal skipped_missing_cell_edges
        base = resolve_quad(cells, cell_vertices)
        if base is None:
            skipped_missing_cell_edges += 1
            return False
        faces.append(
            oriented_quad(
                base,
                lower_value=lower,
                upper_value=upper,
                iso_level=iso_level,
            )
        )
        return True

    for z in range(height):
        for y in range(depth):
            for x in range(width - 1):
                lower, upper = volume.get(x, y, z), volume.get(x + 1, y, z)
                if not edge_crosses_iso(lower, upper, iso_level):
                    continue
                crossing_grid_edges += 1
                if y == 0 or y >= depth - 1 or z == 0 or z >= height - 1:
                    skipped_boundary_edges += 1
                    continue
                cells = (
                    (x, y - 1, z - 1),
                    (x, y, z - 1),
                    (x, y, z),
                    (x, y - 1, z),
                )
                if append_for_edge(cells, lower, upper):
                    emitted_x_quads += 1

    for z in range(height):
        for y in range(depth - 1):
            for x in range(width):
                lower, upper = volume.get(x, y, z), volume.get(x, y + 1, z)
                if not edge_crosses_iso(lower, upper, iso_level):
                    continue
                crossing_grid_edges += 1
                if x == 0 or x >= width - 1 or z == 0 or z >= height - 1:
                    skipped_boundary_edges += 1
                    continue
                cells = (
                    (x - 1, y, z - 1),
                    (x - 1, y, z),
                    (x, y, z),
                    (x, y, z - 1),
                )
                if append_for_edge(cells, lower, upper):
                    emitted_y_quads += 1

    for z in range(height - 1):
        for y in range(depth):
            for x in range(width):
                lower, upper = volume.get(x, y, z), volume.get(x, y, z + 1)
                if not edge_crosses_iso(lower, upper, iso_level):
                    continue
                crossing_grid_edges += 1
                if x == 0 or x >= width - 1 or y == 0 or y >= depth - 1:
                    skipped_boundary_edges += 1
                    continue
                cells = (
                    (x - 1, y - 1, z),
                    (x, y - 1, z),
                    (x, y, z),
                    (x - 1, y, z),
                )
                if append_for_edge(cells, lower, upper):
                    emitted_z_quads += 1

    return (
        faces,
        crossing_grid_edges,
        emitted_x_quads,
        emitted_y_quads,
        emitted_z_quads,
        skipped_boundary_edges,
        skipped_missing_cell_edges,
    )
