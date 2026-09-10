from __future__ import annotations

import math

from dataclasses import dataclass

from .projection_math import (
    grid_to_normalized,
)
from .sdf import (
    SDFVolume,
)


# =========================================================
# Types / constants
# =========================================================

Vector3 = tuple[
    float,
    float,
    float,
]

CellCoordinate = tuple[
    int,
    int,
    int,
]

Quad = tuple[
    int,
    int,
    int,
    int,
]

Triangle = tuple[
    int,
    int,
    int,
]


EPSILON = 1e-9

DEFAULT_GRADIENT_STEP_SCALE = 0.5

DEFAULT_GENERATE_NORMALS = True


# ---------------------------------------------------------
# Cube topology
#
#        7 -------- 6
#       /|         /|
#      4 -------- 5 |
#      | |        | |
#      | 3 -------|-2
#      |/         |/
#      0 -------- 1
# ---------------------------------------------------------

CUBE_CORNERS: tuple[
    tuple[
        int,
        int,
        int,
    ],
    ...,
] = (
    (0, 0, 0),
    (1, 0, 0),
    (1, 1, 0),
    (0, 1, 0),

    (0, 0, 1),
    (1, 0, 1),
    (1, 1, 1),
    (0, 1, 1),
)


CUBE_EDGES: tuple[
    tuple[
        int,
        int,
    ],
    ...,
] = (
    # Bottom
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),

    # Top
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),

    # Vertical
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
)


# =========================================================
# Configuration
# =========================================================

@dataclass(frozen=True)
class SDFSurfaceConfig:
    """
    Surface Nets extraction configuration.

    iso_level=None:
        use SDFVolume.iso_level.

    gradient_step_scale:
        gradient sampling distance relative to one scalar-grid
        interval.

    generate_normals:
        estimate normals directly from the SDF gradient.
    """

    iso_level: float | None = None

    gradient_step_scale: float = (
        DEFAULT_GRADIENT_STEP_SCALE
    )

    generate_normals: bool = (
        DEFAULT_GENERATE_NORMALS
    )

    def validate(
        self,
    ) -> None:
        if self.iso_level is not None:
            if not math.isfinite(
                float(
                    self.iso_level
                )
            ):
                raise ValueError(
                    (
                        "iso_level must "
                        "be finite."
                    )
                )

        if (
            not math.isfinite(
                float(
                    self.gradient_step_scale
                )
            )
            or self.gradient_step_scale
            <= 0.0
        ):
            raise ValueError(
                (
                    "gradient_step_scale "
                    "must be finite and "
                    "greater than zero."
                )
            )

    def resolved_iso_level(
        self,
        volume: SDFVolume,
    ) -> float:
        if self.iso_level is None:
            return float(
                volume.iso_level
            )

        return float(
            self.iso_level
        )


# =========================================================
# Surface data
# =========================================================

@dataclass(frozen=True)
class SDFSurfaceVertex:
    """
    One Surface Nets vertex.

    position:
        normalized reconstruction coordinates [-1, +1].

    normal:
        outward SDF gradient.

    cell:
        source scalar-grid cell.

    intersection_count:
        number of unique iso-edge intersections averaged to
        produce the vertex.
    """

    position: Vector3

    normal: Vector3

    cell: CellCoordinate

    intersection_count: int


@dataclass(frozen=True)
class SDFSurfaceMesh:
    """
    Algorithm-neutral surface produced from an SDFVolume.

    Coordinates remain NORMALIZED here.

    Conversion to Meshvenn's GeometryProjectionSpace is the
    responsibility of the Blender GEOMETRY implementation.
    """

    vertices: tuple[
        SDFSurfaceVertex,
        ...,
    ]

    faces: tuple[
        Quad,
        ...,
    ]

    source_dimensions: tuple[
        int,
        int,
        int,
    ]

    iso_level: float

    def __post_init__(
        self,
    ) -> None:
        width, depth, height = (
            self.source_dimensions
        )

        if (
            width < 2
            or depth < 2
            or height < 2
        ):
            raise ValueError(
                (
                    "source_dimensions must "
                    "all be >= 2."
                )
            )

        if not math.isfinite(
            float(
                self.iso_level
            )
        ):
            raise ValueError(
                (
                    "iso_level must "
                    "be finite."
                )
            )

        vertex_count = len(
            self.vertices
        )

        for face in self.faces:
            if len(
                face
            ) != 4:
                raise ValueError(
                    (
                        "Surface Nets faces "
                        "must contain 4 indices."
                    )
                )

            if len(
                set(
                    face
                )
            ) != 4:
                raise ValueError(
                    (
                        "Surface Nets face "
                        "contains duplicate vertices."
                    )
                )

            for index in face:
                if (
                    index < 0
                    or index >= vertex_count
                ):
                    raise ValueError(
                        (
                            "Surface Nets face "
                            "contains an invalid "
                            "vertex index."
                        )
                    )

    @property
    def vertex_count(
        self,
    ) -> int:
        return len(
            self.vertices
        )

    @property
    def polygon_count(
        self,
    ) -> int:
        return len(
            self.faces
        )

    @property
    def quad_count(
        self,
    ) -> int:
        return (
            self.polygon_count
        )

    @property
    def triangle_count(
        self,
    ) -> int:
        return (
            self.quad_count
            * 2
        )

    @property
    def index_count(
        self,
    ) -> int:
        return (
            self.quad_count
            * 4
        )

    @property
    def empty(
        self,
    ) -> bool:
        return (
            self.vertex_count == 0
        )

    @property
    def positions(
        self,
    ) -> tuple[
        Vector3,
        ...,
    ]:
        return tuple(
            vertex.position
            for vertex
            in self.vertices
        )

    @property
    def normals(
        self,
    ) -> tuple[
        Vector3,
        ...,
    ]:
        return tuple(
            vertex.normal
            for vertex
            in self.vertices
        )

    @property
    def bounds(
        self,
    ) -> (
        tuple[
            Vector3,
            Vector3,
        ]
        | None
    ):
        if not self.vertices:
            return None

        positions = (
            self.positions
        )

        minimum = (
            min(
                value[0]
                for value
                in positions
            ),
            min(
                value[1]
                for value
                in positions
            ),
            min(
                value[2]
                for value
                in positions
            ),
        )

        maximum = (
            max(
                value[0]
                for value
                in positions
            ),
            max(
                value[1]
                for value
                in positions
            ),
            max(
                value[2]
                for value
                in positions
            ),
        )

        return (
            minimum,
            maximum,
        )

    def triangulated_faces(
        self,
    ) -> tuple[
        Triangle,
        ...,
    ]:
        """
        Deterministic quad triangulation.

            a ---- b
            |    / |
            |  /   |
            |/     |
            d ---- c

        becomes:

            a,b,c
            a,c,d
        """

        result: list[
            Triangle
        ] = []

        for (
            a,
            b,
            c,
            d,
        ) in self.faces:
            result.append(
                (
                    a,
                    b,
                    c,
                )
            )

            result.append(
                (
                    a,
                    c,
                    d,
                )
            )

        return tuple(
            result
        )


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
    def active_cell_ratio(
        self,
    ) -> float:
        if self.cell_count <= 0:
            return 0.0

        return (
            float(
                self.active_cells
            )
            / float(
                self.cell_count
            )
        )


@dataclass(frozen=True)
class SDFSurfaceResult:
    mesh: SDFSurfaceMesh

    stats: SDFSurfaceStats

    config: SDFSurfaceConfig


# =========================================================
# Numeric helpers
# =========================================================

def _clamp01(
    value: float,
) -> float:
    return max(
        0.0,
        min(
            1.0,
            float(
                value
            ),
        ),
    )


def _normalize3(
    value: Vector3,
) -> Vector3:
    length = math.sqrt(
        value[0] * value[0]
        + value[1] * value[1]
        + value[2] * value[2]
    )

    if length <= EPSILON:
        return (
            0.0,
            0.0,
            0.0,
        )

    inverse = (
        1.0
        / length
    )

    return (
        value[0]
        * inverse,

        value[1]
        * inverse,

        value[2]
        * inverse,
    )


def _average_points(
    values: list[
        Vector3
    ],
) -> Vector3:
    if not values:
        raise ValueError(
            (
                "Cannot average an "
                "empty point collection."
            )
        )

    inverse = (
        1.0
        / float(
            len(
                values
            )
        )
    )

    return (
        sum(
            value[0]
            for value
            in values
        )
        * inverse,

        sum(
            value[1]
            for value
            in values
        )
        * inverse,

        sum(
            value[2]
            for value
            in values
        )
        * inverse,
    )


def _edge_crosses_iso(
    first: float,
    second: float,
    iso_level: float,
) -> bool:
    """
    Stable binary topology classification.

    Exactly-on-iso samples belong to the inside side.

    Surface topology is therefore generated when the two
    endpoints have different inside/outside classifications.
    """

    first_inside = (
        float(
            first
        )
        <= iso_level
    )

    second_inside = (
        float(
            second
        )
        <= iso_level
    )

    return (
        first_inside
        != second_inside
    )


def _edge_interpolation(
    first: float,
    second: float,
    iso_level: float,
) -> float:
    denominator = (
        float(
            second
        )
        - float(
            first
        )
    )

    if abs(
        denominator
    ) <= EPSILON:
        return 0.5

    return _clamp01(
        (
            iso_level
            - float(
                first
            )
        )
        / denominator
    )


def _interpolate3(
    first: Vector3,
    second: Vector3,
    factor: float,
) -> Vector3:
    return (
        first[0]
        + (
            second[0]
            - first[0]
        )
        * factor,

        first[1]
        + (
            second[1]
            - first[1]
        )
        * factor,

        first[2]
        + (
            second[2]
            - first[2]
        )
        * factor,
    )


def _append_unique_point(
    values: list[
        Vector3
    ],
    point: Vector3,
) -> None:
    """
    Iso-surfaces exactly touching a grid corner can make
    multiple cube edges produce the same intersection.

    Do not let that corner receive artificial extra weight in
    the Surface Nets average.
    """

    for existing in values:
        if (
            abs(
                existing[0]
                - point[0]
            )
            <= EPSILON
            and abs(
                existing[1]
                - point[1]
            )
            <= EPSILON
            and abs(
                existing[2]
                - point[2]
            )
            <= EPSILON
        ):
            return

    values.append(
        point
    )


# =========================================================
# Normalized grid coordinates
# =========================================================

def _normalized_grid_position(
    volume: SDFVolume,
    x: int,
    y: int,
    z: int,
) -> Vector3:
    return (
        grid_to_normalized(
            x,
            volume.width,
        ),

        grid_to_normalized(
            y,
            volume.depth,
        ),

        grid_to_normalized(
            z,
            volume.height,
        ),
    )


# =========================================================
# SDF normal
# =========================================================

def estimate_sdf_normal(
    volume: SDFVolume,
    position: Vector3,
    *,
    step_scale: float = (
        DEFAULT_GRADIENT_STEP_SCALE
    ),
) -> Vector3:
    """
    Estimate the SDF gradient at a normalized position.

    Since Meshvenn's sign convention is:

        negative = inside
        positive = outside

    the gradient naturally points OUTWARD.
    """

    step_scale = float(
        step_scale
    )

    if (
        not math.isfinite(
            step_scale
        )
        or step_scale <= 0.0
    ):
        raise ValueError(
            (
                "step_scale must "
                "be finite and positive."
            )
        )

    hx = (
        (
            2.0
            / float(
                volume.width
                - 1
            )
        )
        * step_scale
    )

    hy = (
        (
            2.0
            / float(
                volume.depth
                - 1
            )
        )
        * step_scale
    )

    hz = (
        (
            2.0
            / float(
                volume.height
                - 1
            )
        )
        * step_scale
    )

    x, y, z = (
        position
    )

    dx = (
        volume.sample_normalized(
            x + hx,
            y,
            z,
        )
        - volume.sample_normalized(
            x - hx,
            y,
            z,
        )
    ) / (
        2.0
        * hx
    )

    dy = (
        volume.sample_normalized(
            x,
            y + hy,
            z,
        )
        - volume.sample_normalized(
            x,
            y - hy,
            z,
        )
    ) / (
        2.0
        * hy
    )

    dz = (
        volume.sample_normalized(
            x,
            y,
            z + hz,
        )
        - volume.sample_normalized(
            x,
            y,
            z - hz,
        )
    ) / (
        2.0
        * hz
    )

    return _normalize3(
        (
            dx,
            dy,
            dz,
        )
    )


# =========================================================
# Cell extraction
# =========================================================

def _extract_cell_vertex(
    volume: SDFVolume,
    *,
    x: int,
    y: int,
    z: int,
    iso_level: float,
    config: SDFSurfaceConfig,
) -> (
    SDFSurfaceVertex
    | None
):
    corner_values: list[
        float
    ] = []

    corner_positions: list[
        Vector3
    ] = []

    for (
        offset_x,
        offset_y,
        offset_z,
    ) in CUBE_CORNERS:
        gx = (
            x
            + offset_x
        )

        gy = (
            y
            + offset_y
        )

        gz = (
            z
            + offset_z
        )

        corner_values.append(
            volume.get(
                gx,
                gy,
                gz,
            )
        )

        corner_positions.append(
            _normalized_grid_position(
                volume,
                gx,
                gy,
                gz,
            )
        )

    intersections: list[
        Vector3
    ] = []

    for (
        first_index,
        second_index,
    ) in CUBE_EDGES:
        first_value = (
            corner_values[
                first_index
            ]
        )

        second_value = (
            corner_values[
                second_index
            ]
        )

        if not _edge_crosses_iso(
            first_value,
            second_value,
            iso_level,
        ):
            continue

        factor = (
            _edge_interpolation(
                first_value,
                second_value,
                iso_level,
            )
        )

        point = (
            _interpolate3(
                corner_positions[
                    first_index
                ],
                corner_positions[
                    second_index
                ],
                factor,
            )
        )

        _append_unique_point(
            intersections,
            point,
        )

    if not intersections:
        return None

    position = (
        _average_points(
            intersections
        )
    )

    if config.generate_normals:
        normal = (
            estimate_sdf_normal(
                volume,
                position,
                step_scale=(
                    config
                    .gradient_step_scale
                ),
            )
        )

    else:
        normal = (
            0.0,
            0.0,
            0.0,
        )

    return SDFSurfaceVertex(
        position=(
            position
        ),

        normal=(
            normal
        ),

        cell=(
            x,
            y,
            z,
        ),

        intersection_count=len(
            intersections
        ),
    )


# =========================================================
# Face helpers
# =========================================================

def _oriented_quad(
    base: Quad,
    *,
    lower_value: float,
    upper_value: float,
    iso_level: float,
) -> Quad:
    """
    `base` has normal pointing toward the positive direction
    of its grid axis.

    If the field goes:

        inside -> outside

    along that positive axis, base already points outward.

    Otherwise reverse its winding.
    """

    lower_inside = (
        lower_value
        <= iso_level
    )

    upper_inside = (
        upper_value
        <= iso_level
    )

    if (
        lower_inside
        and not upper_inside
    ):
        return base

    return (
        base[0],
        base[3],
        base[2],
        base[1],
    )


def _resolve_quad(
    cells: tuple[
        CellCoordinate,
        CellCoordinate,
        CellCoordinate,
        CellCoordinate,
    ],
    cell_vertices: dict[
        CellCoordinate,
        int,
    ],
) -> (
    Quad
    | None
):
    try:
        return (
            cell_vertices[
                cells[0]
            ],
            cell_vertices[
                cells[1]
            ],
            cell_vertices[
                cells[2]
            ],
            cell_vertices[
                cells[3]
            ],
        )

    except KeyError:
        return None


# =========================================================
# Surface Nets extraction
# =========================================================

def extract_surface_nets(
    volume: SDFVolume,
    *,
    config: (
        SDFSurfaceConfig
        | None
    ) = None,
) -> SDFSurfaceResult:
    """
    Extract one quad-dominant Surface Nets mesh directly from
    the continuous SDF.

    Algorithm:

        scalar grid
            ↓
        find sign-changing cells
            ↓
        interpolate every crossing edge
            ↓
        average crossings
            ↓
        one vertex per active cell
            ↓
        one quad per sign-changing grid edge

    Unlike binary voxel meshing, the generated vertex
    positions move continuously with the scalar field.
    """

    if not isinstance(
        volume,
        SDFVolume,
    ):
        raise TypeError(
            (
                "volume must be "
                "SDFVolume."
            )
        )

    if config is None:
        config = (
            SDFSurfaceConfig()
        )

    if not isinstance(
        config,
        SDFSurfaceConfig,
    ):
        raise TypeError(
            (
                "config must be "
                "SDFSurfaceConfig."
            )
        )

    config.validate()

    iso_level = (
        config.resolved_iso_level(
            volume
        )
    )

    width = (
        volume.width
    )

    depth = (
        volume.depth
    )

    height = (
        volume.height
    )

    vertices: list[
        SDFSurfaceVertex
    ] = []

    cell_vertices: dict[
        CellCoordinate,
        int,
    ] = {}

    unique_cell_intersections = 0

    # -----------------------------------------------------
    # 1. One vertex for each sign-changing cell
    # -----------------------------------------------------

    for z in range(
        height - 1
    ):
        for y in range(
            depth - 1
        ):
            for x in range(
                width - 1
            ):
                vertex = (
                    _extract_cell_vertex(
                        volume,
                        x=x,
                        y=y,
                        z=z,
                        iso_level=(
                            iso_level
                        ),
                        config=config,
                    )
                )

                if vertex is None:
                    continue

                index = len(
                    vertices
                )

                vertices.append(
                    vertex
                )

                cell_vertices[
                    (
                        x,
                        y,
                        z,
                    )
                ] = index

                unique_cell_intersections += (
                    vertex
                    .intersection_count
                )

    faces: list[
        Quad
    ] = []

    crossing_grid_edges = 0

    emitted_x_quads = 0

    emitted_y_quads = 0

    emitted_z_quads = 0

    skipped_boundary_edges = 0

    skipped_missing_cell_edges = 0

    # -----------------------------------------------------
    # 2. X-aligned grid edges
    #
    # Base winding normal = +X.
    # -----------------------------------------------------

    for z in range(
        height
    ):
        for y in range(
            depth
        ):
            for x in range(
                width - 1
            ):
                lower = (
                    volume.get(
                        x,
                        y,
                        z,
                    )
                )

                upper = (
                    volume.get(
                        x + 1,
                        y,
                        z,
                    )
                )

                if not _edge_crosses_iso(
                    lower,
                    upper,
                    iso_level,
                ):
                    continue

                crossing_grid_edges += 1

                if (
                    y == 0
                    or y >= depth - 1
                    or z == 0
                    or z >= height - 1
                ):
                    skipped_boundary_edges += 1

                    continue

                cells = (
                    (
                        x,
                        y - 1,
                        z - 1,
                    ),
                    (
                        x,
                        y,
                        z - 1,
                    ),
                    (
                        x,
                        y,
                        z,
                    ),
                    (
                        x,
                        y - 1,
                        z,
                    ),
                )

                base = (
                    _resolve_quad(
                        cells,
                        cell_vertices,
                    )
                )

                if base is None:
                    skipped_missing_cell_edges += 1

                    continue

                faces.append(
                    _oriented_quad(
                        base,
                        lower_value=lower,
                        upper_value=upper,
                        iso_level=(
                            iso_level
                        ),
                    )
                )

                emitted_x_quads += 1

    # -----------------------------------------------------
    # 3. Y-aligned grid edges
    #
    # Base winding normal = +Y.
    # -----------------------------------------------------

    for z in range(
        height
    ):
        for y in range(
            depth - 1
        ):
            for x in range(
                width
            ):
                lower = (
                    volume.get(
                        x,
                        y,
                        z,
                    )
                )

                upper = (
                    volume.get(
                        x,
                        y + 1,
                        z,
                    )
                )

                if not _edge_crosses_iso(
                    lower,
                    upper,
                    iso_level,
                ):
                    continue

                crossing_grid_edges += 1

                if (
                    x == 0
                    or x >= width - 1
                    or z == 0
                    or z >= height - 1
                ):
                    skipped_boundary_edges += 1

                    continue

                cells = (
                    (
                        x - 1,
                        y,
                        z - 1,
                    ),
                    (
                        x - 1,
                        y,
                        z,
                    ),
                    (
                        x,
                        y,
                        z,
                    ),
                    (
                        x,
                        y,
                        z - 1,
                    ),
                )

                base = (
                    _resolve_quad(
                        cells,
                        cell_vertices,
                    )
                )

                if base is None:
                    skipped_missing_cell_edges += 1

                    continue

                faces.append(
                    _oriented_quad(
                        base,
                        lower_value=lower,
                        upper_value=upper,
                        iso_level=(
                            iso_level
                        ),
                    )
                )

                emitted_y_quads += 1

    # -----------------------------------------------------
    # 4. Z-aligned grid edges
    #
    # Base winding normal = +Z.
    # -----------------------------------------------------

    for z in range(
        height - 1
    ):
        for y in range(
            depth
        ):
            for x in range(
                width
            ):
                lower = (
                    volume.get(
                        x,
                        y,
                        z,
                    )
                )

                upper = (
                    volume.get(
                        x,
                        y,
                        z + 1,
                    )
                )

                if not _edge_crosses_iso(
                    lower,
                    upper,
                    iso_level,
                ):
                    continue

                crossing_grid_edges += 1

                if (
                    x == 0
                    or x >= width - 1
                    or y == 0
                    or y >= depth - 1
                ):
                    skipped_boundary_edges += 1

                    continue

                cells = (
                    (
                        x - 1,
                        y - 1,
                        z,
                    ),
                    (
                        x,
                        y - 1,
                        z,
                    ),
                    (
                        x,
                        y,
                        z,
                    ),
                    (
                        x - 1,
                        y,
                        z,
                    ),
                )

                base = (
                    _resolve_quad(
                        cells,
                        cell_vertices,
                    )
                )

                if base is None:
                    skipped_missing_cell_edges += 1

                    continue

                faces.append(
                    _oriented_quad(
                        base,
                        lower_value=lower,
                        upper_value=upper,
                        iso_level=(
                            iso_level
                        ),
                    )
                )

                emitted_z_quads += 1

    # -----------------------------------------------------
    # Result
    # -----------------------------------------------------

    mesh = (
        SDFSurfaceMesh(
            vertices=tuple(
                vertices
            ),

            faces=tuple(
                faces
            ),

            source_dimensions=(
                width,
                depth,
                height,
            ),

            iso_level=(
                iso_level
            ),
        )
    )

    stats = (
        SDFSurfaceStats(
            cell_count=(
                (
                    width - 1
                )
                * (
                    depth - 1
                )
                * (
                    height - 1
                )
            ),

            active_cells=len(
                vertices
            ),

            unique_cell_intersections=(
                unique_cell_intersections
            ),

            crossing_grid_edges=(
                crossing_grid_edges
            ),

            emitted_quads=len(
                faces
            ),

            emitted_x_quads=(
                emitted_x_quads
            ),

            emitted_y_quads=(
                emitted_y_quads
            ),

            emitted_z_quads=(
                emitted_z_quads
            ),

            skipped_boundary_edges=(
                skipped_boundary_edges
            ),

            skipped_missing_cell_edges=(
                skipped_missing_cell_edges
            ),
        )
    )

    return SDFSurfaceResult(
        mesh=mesh,
        stats=stats,
        config=config,
    )


# =========================================================
# Public API
# =========================================================

__all__ = (
    "CUBE_CORNERS",
    "CUBE_EDGES",
    "DEFAULT_GENERATE_NORMALS",
    "DEFAULT_GRADIENT_STEP_SCALE",
    "EPSILON",
    "SDFSurfaceConfig",
    "SDFSurfaceMesh",
    "SDFSurfaceResult",
    "SDFSurfaceStats",
    "SDFSurfaceVertex",
    "estimate_sdf_normal",
    "extract_surface_nets",
)