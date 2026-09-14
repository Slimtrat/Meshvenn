from __future__ import annotations

from ..sdf import SDFVolume
from .cells import extract_cell_vertex
from .faces import build_faces
from .models import (
    CellCoordinate,
    SDFSurfaceConfig,
    SDFSurfaceMesh,
    SDFSurfaceResult,
    SDFSurfaceStats,
    SDFSurfaceVertex,
)


def extract_surface_nets(
    volume: SDFVolume,
    *,
    config: SDFSurfaceConfig | None = None,
) -> SDFSurfaceResult:
    """Extract one quad-dominant Surface Nets mesh from a continuous SDF."""

    if not isinstance(volume, SDFVolume):
        raise TypeError("volume must be SDFVolume.")
    if config is None:
        config = SDFSurfaceConfig()
    if not isinstance(config, SDFSurfaceConfig):
        raise TypeError("config must be SDFSurfaceConfig.")
    config.validate()

    iso_level = config.resolved_iso_level(volume)
    width, depth, height = volume.width, volume.depth, volume.height
    vertices: list[SDFSurfaceVertex] = []
    cell_vertices: dict[CellCoordinate, int] = {}
    unique_cell_intersections = 0

    for z in range(height - 1):
        for y in range(depth - 1):
            for x in range(width - 1):
                vertex = extract_cell_vertex(
                    volume,
                    x=x,
                    y=y,
                    z=z,
                    iso_level=iso_level,
                    config=config,
                )
                if vertex is None:
                    continue
                cell_vertices[(x, y, z)] = len(vertices)
                vertices.append(vertex)
                unique_cell_intersections += vertex.intersection_count

    (
        faces,
        crossing_grid_edges,
        emitted_x_quads,
        emitted_y_quads,
        emitted_z_quads,
        skipped_boundary_edges,
        skipped_missing_cell_edges,
    ) = build_faces(volume, cell_vertices, iso_level)

    mesh = SDFSurfaceMesh(
        vertices=tuple(vertices),
        faces=tuple(faces),
        source_dimensions=(width, depth, height),
        iso_level=iso_level,
    )
    stats = SDFSurfaceStats(
        cell_count=(width - 1) * (depth - 1) * (height - 1),
        active_cells=len(vertices),
        unique_cell_intersections=unique_cell_intersections,
        crossing_grid_edges=crossing_grid_edges,
        emitted_quads=len(faces),
        emitted_x_quads=emitted_x_quads,
        emitted_y_quads=emitted_y_quads,
        emitted_z_quads=emitted_z_quads,
        skipped_boundary_edges=skipped_boundary_edges,
        skipped_missing_cell_edges=skipped_missing_cell_edges,
    )
    return SDFSurfaceResult(mesh=mesh, stats=stats, config=config)
