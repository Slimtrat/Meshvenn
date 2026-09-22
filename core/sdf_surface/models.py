from __future__ import annotations

import math
from dataclasses import dataclass

from ..sdf import SDFVolume


Vector3 = tuple[float, float, float]
CellCoordinate = tuple[int, int, int]
Quad = tuple[int, int, int, int]
Triangle = tuple[int, int, int]

EPSILON = 1e-9
DEFAULT_GRADIENT_STEP_SCALE = 0.5
DEFAULT_GENERATE_NORMALS = True


@dataclass(frozen=True)
class SDFSurfaceConfig:
    """Surface Nets extraction configuration."""

    iso_level: float | None = None
    gradient_step_scale: float = DEFAULT_GRADIENT_STEP_SCALE
    generate_normals: bool = DEFAULT_GENERATE_NORMALS

    def validate(self) -> None:
        if self.iso_level is not None and not math.isfinite(float(self.iso_level)):
            raise ValueError("iso_level must be finite.")
        if (
            not math.isfinite(float(self.gradient_step_scale))
            or self.gradient_step_scale <= 0.0
        ):
            raise ValueError(
                "gradient_step_scale must be finite and greater than zero."
            )

    def resolved_iso_level(self, volume: SDFVolume) -> float:
        if self.iso_level is None:
            return float(volume.iso_level)
        return float(self.iso_level)


@dataclass(frozen=True)
class SDFSurfaceVertex:
    """One Surface Nets vertex in normalized reconstruction coordinates."""

    position: Vector3
    normal: Vector3
    cell: CellCoordinate
    intersection_count: int


@dataclass(frozen=True)
class SDFSurfaceMesh:
    """Algorithm-neutral surface produced from an SDFVolume."""

    vertices: tuple[SDFSurfaceVertex, ...]
    faces: tuple[Quad, ...]
    source_dimensions: tuple[int, int, int]
    iso_level: float

    def __post_init__(self) -> None:
        width, depth, height = self.source_dimensions
        if width < 2 or depth < 2 or height < 2:
            raise ValueError("source_dimensions must all be >= 2.")
        if not math.isfinite(float(self.iso_level)):
            raise ValueError("iso_level must be finite.")
        vertex_count = len(self.vertices)
        for face in self.faces:
            if len(face) != 4:
                raise ValueError("Surface Nets faces must contain 4 indices.")
            if len(set(face)) != 4:
                raise ValueError("Surface Nets face contains duplicate vertices.")
            for index in face:
                if index < 0 or index >= vertex_count:
                    raise ValueError(
                        "Surface Nets face contains an invalid vertex index."
                    )

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def polygon_count(self) -> int:
        return len(self.faces)

    @property
    def quad_count(self) -> int:
        return self.polygon_count

    @property
    def triangle_count(self) -> int:
        return self.quad_count * 2

    @property
    def index_count(self) -> int:
        return self.quad_count * 4

    @property
    def empty(self) -> bool:
        return self.vertex_count == 0

    @property
    def positions(self) -> tuple[Vector3, ...]:
        return tuple(vertex.position for vertex in self.vertices)

    @property
    def normals(self) -> tuple[Vector3, ...]:
        return tuple(vertex.normal for vertex in self.vertices)

    @property
    def bounds(self) -> tuple[Vector3, Vector3] | None:
        if not self.vertices:
            return None
        positions = self.positions
        minimum = (
            min(value[0] for value in positions),
            min(value[1] for value in positions),
            min(value[2] for value in positions),
        )
        maximum = (
            max(value[0] for value in positions),
            max(value[1] for value in positions),
            max(value[2] for value in positions),
        )
        return minimum, maximum

    def triangulated_faces(self) -> tuple[Triangle, ...]:
        result: list[Triangle] = []
        for a, b, c, d in self.faces:
            result.append((a, b, c))
            result.append((a, c, d))
        return tuple(result)


@dataclass(frozen=True)
class SDFSurfaceStats:
    cell_count: int
    active_cells: int
    unique_cell_intersections: int
    crossing_grid_edges: int
    emitted_quads: int
    emitted_x_quads: int
    emitted_y_quads: int
    emitted_z_quads: int
    skipped_boundary_edges: int
    skipped_missing_cell_edges: int

    @property
    def active_cell_ratio(self) -> float:
        if self.cell_count <= 0:
            return 0.0
        return float(self.active_cells) / float(self.cell_count)


@dataclass(frozen=True)
class SDFSurfaceResult:
    mesh: SDFSurfaceMesh
    stats: SDFSurfaceStats
    config: SDFSurfaceConfig
