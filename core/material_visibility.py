from __future__ import annotations

import math

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    TypeAlias,
)


# ---------------------------------------------------------
# Types
# ---------------------------------------------------------

Vector3: TypeAlias = tuple[
    float,
    float,
    float,
]


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

DEFAULT_RELATIVE_EPSILON = 1e-5

DEFAULT_ABSOLUTE_EPSILON = 1e-6

DEFAULT_RAY_LENGTH_MULTIPLIER = 2.0

MIN_DIRECTION_LENGTH = 1e-12

MIN_RAY_DISTANCE = 1e-6


# ---------------------------------------------------------
# Raycast result
# ---------------------------------------------------------

@dataclass(frozen=True)
class RaycastHit:
    """
    Backend-independent representation of one ray hit.

    `distance` is measured from the ray origin.

    `polygon_index` is optional because pure Python tests
    do not need to emulate Blender polygon identifiers.
    """

    distance: float

    polygon_index: int | None = None

    position: Vector3 | None = None

    normal: Vector3 | None = None


RaycastFunction: TypeAlias = Callable[
    [
        Vector3,
        Vector3,
        float,
    ],
    RaycastHit | None,
]


# ---------------------------------------------------------
# Visibility configuration
# ---------------------------------------------------------

@dataclass(frozen=True)
class VisibilityConfig:
    """
    Numerical configuration for mesh visibility queries.

    relative_epsilon:
        Scale-relative surface offset.

        The effective epsilon is:

            max(
                absolute_epsilon,
                mesh_diagonal
                * relative_epsilon,
            )

    absolute_epsilon:
        Minimum offset even for very small meshes.

    ray_length_multiplier:
        Maximum ray distance expressed relative to the
        bounding-box diagonal.

        A value greater than 1 is sufficient for an
        orthographic visibility query because any
        occluding geometry must remain inside the mesh
        bounding box.
    """

    relative_epsilon: float = (
        DEFAULT_RELATIVE_EPSILON
    )

    absolute_epsilon: float = (
        DEFAULT_ABSOLUTE_EPSILON
    )

    ray_length_multiplier: float = (
        DEFAULT_RAY_LENGTH_MULTIPLIER
    )

    def validate(
        self,
    ) -> None:
        if (
            not math.isfinite(
                self.relative_epsilon
            )
            or self.relative_epsilon
            < 0.0
        ):
            raise ValueError(
                (
                    "relative_epsilon must be "
                    "finite and >= 0."
                )
            )

        if (
            not math.isfinite(
                self.absolute_epsilon
            )
            or self.absolute_epsilon
            <= 0.0
        ):
            raise ValueError(
                (
                    "absolute_epsilon must be "
                    "finite and > 0."
                )
            )

        if (
            not math.isfinite(
                self.ray_length_multiplier
            )
            or self.ray_length_multiplier
            <= 1.0
        ):
            raise ValueError(
                (
                    "ray_length_multiplier must "
                    "be finite and > 1."
                )
            )


# ---------------------------------------------------------
# Visibility result
# ---------------------------------------------------------

@dataclass(frozen=True)
class VisibilityResult:
    """
    Result of one surface -> camera visibility test.
    """

    visible: bool

    occluded: bool

    hit_distance: float | None = None

    polygon_index: int | None = None

    @classmethod
    def clear(
        cls,
    ) -> "VisibilityResult":
        return cls(
            visible=True,
            occluded=False,
            hit_distance=None,
            polygon_index=None,
        )

    @classmethod
    def blocked(
        cls,
        hit: RaycastHit,
    ) -> "VisibilityResult":
        return cls(
            visible=False,
            occluded=True,
            hit_distance=(
                float(
                    hit.distance
                )
            ),
            polygon_index=(
                hit.polygon_index
            ),
        )


# ---------------------------------------------------------
# Small vector helpers
# ---------------------------------------------------------

def _vector_length(
    value: Vector3,
) -> float:
    return math.sqrt(
        (
            float(
                value[0]
            )
            ** 2
        )
        + (
            float(
                value[1]
            )
            ** 2
        )
        + (
            float(
                value[2]
            )
            ** 2
        )
    )


def _normalize(
    value: Vector3,
) -> Vector3:
    length = _vector_length(
        value
    )

    if (
        not math.isfinite(
            length
        )
        or length
        <= MIN_DIRECTION_LENGTH
    ):
        raise ValueError(
            (
                "Visibility ray direction "
                "must be a finite, non-zero "
                "vector."
            )
        )

    inverse = (
        1.0
        / length
    )

    result = (
        float(
            value[0]
        )
        * inverse,
        float(
            value[1]
        )
        * inverse,
        float(
            value[2]
        )
        * inverse,
    )

    if not all(
        math.isfinite(
            component
        )
        for component in result
    ):
        raise ValueError(
            (
                "Visibility ray direction "
                "contains non-finite values."
            )
        )

    return result


def _offset_point(
    position: Vector3,
    direction: Vector3,
    distance: float,
) -> Vector3:
    return (
        float(
            position[0]
        )
        + direction[0]
        * distance,
        float(
            position[1]
        )
        + direction[1]
        * distance,
        float(
            position[2]
        )
        + direction[2]
        * distance,
    )


def _validate_position(
    position: Vector3,
) -> Vector3:
    result = (
        float(
            position[0]
        ),
        float(
            position[1]
        ),
        float(
            position[2]
        ),
    )

    if not all(
        math.isfinite(
            component
        )
        for component in result
    ):
        raise ValueError(
            (
                "Visibility position contains "
                "non-finite values."
            )
        )

    return result


# ---------------------------------------------------------
# Bounding box
# ---------------------------------------------------------

def bounding_box_diagonal(
    vertices: list[
        Vector3
    ],
) -> float:
    """
    Return the diagonal of an axis-aligned bounding box.
    """

    if not vertices:
        raise ValueError(
            (
                "Cannot compute visibility bounds "
                "for an empty vertex list."
            )
        )

    first = _validate_position(
        vertices[0]
    )

    minimum_x = first[0]
    minimum_y = first[1]
    minimum_z = first[2]

    maximum_x = first[0]
    maximum_y = first[1]
    maximum_z = first[2]

    for vertex in vertices[1:]:
        (
            x,
            y,
            z,
        ) = _validate_position(
            vertex
        )

        minimum_x = min(
            minimum_x,
            x,
        )

        minimum_y = min(
            minimum_y,
            y,
        )

        minimum_z = min(
            minimum_z,
            z,
        )

        maximum_x = max(
            maximum_x,
            x,
        )

        maximum_y = max(
            maximum_y,
            y,
        )

        maximum_z = max(
            maximum_z,
            z,
        )

    delta_x = (
        maximum_x
        - minimum_x
    )

    delta_y = (
        maximum_y
        - minimum_y
    )

    delta_z = (
        maximum_z
        - minimum_z
    )

    return math.sqrt(
        delta_x
        * delta_x
        + delta_y
        * delta_y
        + delta_z
        * delta_z
    )


# ---------------------------------------------------------
# Effective distances
# ---------------------------------------------------------

def compute_surface_epsilon(
    mesh_diagonal: float,
    config: VisibilityConfig,
) -> float:
    config.validate()

    diagonal = float(
        mesh_diagonal
    )

    if (
        not math.isfinite(
            diagonal
        )
        or diagonal
        < 0.0
    ):
        raise ValueError(
            (
                "mesh_diagonal must be "
                "finite and >= 0."
            )
        )

    return max(
        config.absolute_epsilon,
        diagonal
        * config.relative_epsilon,
    )


def compute_ray_distance(
    mesh_diagonal: float,
    surface_epsilon: float,
    config: VisibilityConfig,
) -> float:
    config.validate()

    diagonal = float(
        mesh_diagonal
    )

    epsilon = float(
        surface_epsilon
    )

    if (
        not math.isfinite(
            diagonal
        )
        or diagonal
        < 0.0
    ):
        raise ValueError(
            (
                "mesh_diagonal must be "
                "finite and >= 0."
            )
        )

    if (
        not math.isfinite(
            epsilon
        )
        or epsilon
        <= 0.0
    ):
        raise ValueError(
            (
                "surface_epsilon must be "
                "finite and > 0."
            )
        )

    return max(
        diagonal
        * config.ray_length_multiplier,
        epsilon
        * 10.0,
        MIN_RAY_DISTANCE,
    )


# ---------------------------------------------------------
# Main tester
# ---------------------------------------------------------

class MeshVisibilityTester:
    """
    Orthographic surface visibility tester.

    The projection system does not use perspective cameras.
    Every source view has one constant camera direction.

    For a surface point P and a direction D pointing from
    the object toward the camera:

        P
        |
        | offset epsilon
        v
        P' -----------------------> camera
                    D

    If another polygon is intersected after P', then P is
    hidden from that source view.

    The tiny offset is essential because P lies directly on
    the source mesh and would otherwise frequently intersect
    its own triangle due to floating-point precision.

    This class intentionally has no hard Blender dependency.
    Tests can provide any `raycast` callback.

    Blender-specific construction is provided by
    `from_blender_object()`.
    """

    def __init__(
        self,
        raycast: RaycastFunction,
        *,
        surface_epsilon: float,
        max_distance: float,
    ) -> None:
        epsilon = float(
            surface_epsilon
        )

        distance = float(
            max_distance
        )

        if (
            not math.isfinite(
                epsilon
            )
            or epsilon
            <= 0.0
        ):
            raise ValueError(
                (
                    "surface_epsilon must be "
                    "finite and > 0."
                )
            )

        if (
            not math.isfinite(
                distance
            )
            or distance
            <= epsilon
        ):
            raise ValueError(
                (
                    "max_distance must be finite "
                    "and greater than "
                    "surface_epsilon."
                )
            )

        if not callable(
            raycast
        ):
            raise TypeError(
                "raycast must be callable."
            )

        self._raycast = raycast

        self.surface_epsilon = (
            epsilon
        )

        self.max_distance = (
            distance
        )

    # -----------------------------------------------------
    # Public query
    # -----------------------------------------------------

    def query(
        self,
        position: Vector3,
        camera_direction: Vector3,
    ) -> VisibilityResult:
        """
        Test whether `position` is directly visible from one
        orthographic source camera.

        `camera_direction` MUST point from the object toward
        the camera.

        Example:

            azimuth 0°
                camera on -Y

                direction = (0, -1, 0)

        A clear ray means the candidate source projection is
        allowed to contribute color.

        Any mesh intersection between the surface point and
        the camera rejects that candidate.
        """

        position = _validate_position(
            position
        )

        direction = _normalize(
            camera_direction
        )

        # -------------------------------------------------
        # Move outside the source surface before casting.
        #
        # We deliberately offset along the CAMERA DIRECTION,
        # not along the vertex normal.
        #
        # For orthographic visibility the ray itself defines
        # which side of the surface we are testing.
        # -------------------------------------------------

        origin = _offset_point(
            position,
            direction,
            self.surface_epsilon,
        )

        ray_distance = (
            self.max_distance
            - self.surface_epsilon
        )

        if (
            ray_distance
            <= MIN_RAY_DISTANCE
        ):
            return (
                VisibilityResult
                .clear()
            )

        hit = self._raycast(
            origin,
            direction,
            ray_distance,
        )

        if hit is None:
            return (
                VisibilityResult
                .clear()
            )

        hit_distance = float(
            hit.distance
        )

        if (
            not math.isfinite(
                hit_distance
            )
            or hit_distance
            < 0.0
        ):
            raise ValueError(
                (
                    "Raycast backend returned "
                    "an invalid hit distance."
                )
            )

        # -------------------------------------------------
        # Defensive self-intersection rejection.
        #
        # The origin is already shifted outside the source
        # point. Some nearly coplanar / non-manifold meshes
        # can nevertheless report a hit at essentially zero
        # distance.
        #
        # That is numerical noise, not an occluder.
        # -------------------------------------------------

        if (
            hit_distance
            <= self.surface_epsilon
        ):
            return (
                VisibilityResult
                .clear()
            )

        if (
            hit_distance
            > ray_distance
        ):
            return (
                VisibilityResult
                .clear()
            )

        return (
            VisibilityResult
            .blocked(
                hit
            )
        )

    def is_visible(
        self,
        position: Vector3,
        camera_direction: Vector3,
    ) -> bool:
        return (
            self.query(
                position,
                camera_direction,
            )
            .visible
        )

    # -----------------------------------------------------
    # Blender factory
    # -----------------------------------------------------

    @classmethod
    def from_blender_object(
        cls,
        obj: Any,
        *,
        config: VisibilityConfig | None = None,
    ) -> "MeshVisibilityTester":
        """
        Build a BVH directly from a Blender mesh object.

        The BVH is intentionally built in MESH LOCAL SPACE.

        This matches projected_material.py, which projects
        `vertex.co` before object normalization/scaling.

        Do not build this tester after changing the mesh
        coordinates unless the material projection uses the
        same transformed coordinates.
        """

        if config is None:
            config = (
                VisibilityConfig()
            )

        config.validate()

        if obj is None:
            raise TypeError(
                (
                    "Visibility target object "
                    "cannot be None."
                )
            )

        object_type = getattr(
            obj,
            "type",
            None,
        )

        if object_type != "MESH":
            raise TypeError(
                (
                    "Visibility target must "
                    "be a mesh object."
                )
            )

        mesh = getattr(
            obj,
            "data",
            None,
        )

        if mesh is None:
            raise TypeError(
                (
                    "Mesh object has no "
                    "mesh data."
                )
            )

        mesh.update()

        vertices: list[
            Vector3
        ] = []

        for vertex in mesh.vertices:
            vertices.append(
                (
                    float(
                        vertex.co.x
                    ),
                    float(
                        vertex.co.y
                    ),
                    float(
                        vertex.co.z
                    ),
                )
            )

        if not vertices:
            raise ValueError(
                (
                    "Cannot build visibility "
                    "BVH from an empty mesh."
                )
            )

        polygons: list[
            tuple[
                int,
                ...,
            ]
        ] = []

        for polygon in mesh.polygons:
            indices = tuple(
                int(
                    index
                )
                for index
                in polygon.vertices
            )

            if len(
                indices
            ) < 3:
                continue

            polygons.append(
                indices
            )

        if not polygons:
            raise ValueError(
                (
                    "Cannot build visibility "
                    "BVH from a mesh without "
                    "polygons."
                )
            )

        diagonal = (
            bounding_box_diagonal(
                vertices
            )
        )

        surface_epsilon = (
            compute_surface_epsilon(
                diagonal,
                config,
            )
        )

        max_distance = (
            compute_ray_distance(
                diagonal,
                surface_epsilon,
                config,
            )
        )

        raycast = (
            _build_blender_bvh_raycast(
                vertices,
                polygons,
            )
        )

        return cls(
            raycast,
            surface_epsilon=(
                surface_epsilon
            ),
            max_distance=(
                max_distance
            ),
        )


# ---------------------------------------------------------
# Blender BVH adapter
# ---------------------------------------------------------

def _build_blender_bvh_raycast(
    vertices: list[
        Vector3
    ],
    polygons: list[
        tuple[
            int,
            ...,
        ]
    ],
) -> RaycastFunction:
    """
    Create a Blender BVHTree-backed callback.

    Importing mathutils happens here rather than at module
    import time so this module remains usable by normal
    Python unit tests.
    """

    try:
        from mathutils import Vector
        from mathutils.bvhtree import (
            BVHTree,
        )

    except ImportError as exc:
        raise RuntimeError(
            (
                "Blender mathutils is required "
                "to build mesh visibility."
            )
        ) from exc

    blender_vertices = [
        Vector(
            (
                vertex[0],
                vertex[1],
                vertex[2],
            )
        )
        for vertex in vertices
    ]

    bvh = (
        BVHTree
        .FromPolygons(
            blender_vertices,
            polygons,
            all_triangles=False,
            epsilon=0.0,
        )
    )

    if bvh is None:
        raise RuntimeError(
            (
                "Blender failed to build "
                "the visibility BVH."
            )
        )

    def raycast(
        origin: Vector3,
        direction: Vector3,
        distance: float,
    ) -> RaycastHit | None:
        blender_origin = Vector(
            (
                origin[0],
                origin[1],
                origin[2],
            )
        )

        blender_direction = Vector(
            (
                direction[0],
                direction[1],
                direction[2],
            )
        )

        (
            hit_position,
            hit_normal,
            polygon_index,
            hit_distance,
        ) = bvh.ray_cast(
            blender_origin,
            blender_direction,
            float(
                distance
            ),
        )

        if (
            hit_position is None
            or hit_distance is None
        ):
            return None

        position_tuple: Vector3 = (
            float(
                hit_position.x
            ),
            float(
                hit_position.y
            ),
            float(
                hit_position.z
            ),
        )

        normal_tuple: Vector3 | None

        if hit_normal is None:
            normal_tuple = None

        else:
            normal_tuple = (
                float(
                    hit_normal.x
                ),
                float(
                    hit_normal.y
                ),
                float(
                    hit_normal.z
                ),
            )

        normalized_polygon_index: (
            int | None
        )

        if polygon_index is None:
            normalized_polygon_index = (
                None
            )

        else:
            normalized_polygon_index = (
                int(
                    polygon_index
                )
            )

        return RaycastHit(
            distance=float(
                hit_distance
            ),
            polygon_index=(
                normalized_polygon_index
            ),
            position=(
                position_tuple
            ),
            normal=(
                normal_tuple
            ),
        )

    return raycast