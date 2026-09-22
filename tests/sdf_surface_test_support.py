from __future__ import annotations

import math
import unittest

from array import array

from core.projection_math import (
    grid_to_normalized,
)
from core.sdf import (
    SDFVolume,
)
from core.sdf_surface import (
    DEFAULT_GENERATE_NORMALS,
    DEFAULT_GRADIENT_STEP_SCALE,
    SDFSurfaceConfig,
    SDFSurfaceMesh,
    SDFSurfaceVertex,
    estimate_sdf_normal,
    extract_surface_nets,
)


# =========================================================
# Helpers
# =========================================================

def analytic_volume(
    resolution: int,
    function,
    *,
    iso_level: float = 0.0,
) -> SDFVolume:
    """
    Sample an analytic scalar field on the exact normalized
    Meshvenn reconstruction grid:

        index 0              -> -1
        index resolution - 1 -> +1
    """

    values = array(
        "f"
    )

    for z in range(
        resolution
    ):
        nz = (
            grid_to_normalized(
                z,
                resolution,
            )
        )

        for y in range(
            resolution
        ):
            ny = (
                grid_to_normalized(
                    y,
                    resolution,
                )
            )

            for x in range(
                resolution
            ):
                nx = (
                    grid_to_normalized(
                        x,
                        resolution,
                    )
                )

                values.append(
                    float(
                        function(
                            nx,
                            ny,
                            nz,
                        )
                    )
                )

    return SDFVolume(
        width=resolution,
        depth=resolution,
        height=resolution,
        values=values,
        iso_level=iso_level,
    )


def plane_x_volume(
    resolution: int = 7,
) -> SDFVolume:
    """
    Exact analytic field:

        d(x, y, z) = x

    Any iso-level therefore produces the plane:

        x = iso
    """

    return analytic_volume(
        resolution,
        lambda x, y, z: x,
    )


def sphere_volume(
    *,
    resolution: int = 13,
    radius: float = 0.6,
) -> SDFVolume:
    """
    Exact analytic sphere SDF sampled on the grid.
    """

    return analytic_volume(
        resolution,
        lambda x, y, z: (
            math.sqrt(
                x * x
                + y * y
                + z * z
            )
            - radius
        ),
    )


def vector_length(
    value,
) -> float:
    return math.sqrt(
        value[0] * value[0]
        + value[1] * value[1]
        + value[2] * value[2]
    )


def dot3(
    first,
    second,
) -> float:
    return (
        first[0]
        * second[0]
        + first[1]
        * second[1]
        + first[2]
        * second[2]
    )


def subtract3(
    first,
    second,
):
    return (
        first[0]
        - second[0],

        first[1]
        - second[1],

        first[2]
        - second[2],
    )


def cross3(
    first,
    second,
):
    return (
        first[1]
        * second[2]
        - first[2]
        * second[1],

        first[2]
        * second[0]
        - first[0]
        * second[2],

        first[0]
        * second[1]
        - first[1]
        * second[0],
    )


def normalized(
    value,
):
    length = vector_length(
        value
    )

    if length <= 1e-12:
        return (
            0.0,
            0.0,
            0.0,
        )

    return (
        value[0]
        / length,

        value[1]
        / length,

        value[2]
        / length,
    )


def face_geometric_normal(
    mesh: SDFSurfaceMesh,
    face,
):
    first = (
        mesh.vertices[
            face[0]
        ].position
    )

    second = (
        mesh.vertices[
            face[1]
        ].position
    )

    third = (
        mesh.vertices[
            face[2]
        ].position
    )

    edge_a = subtract3(
        second,
        first,
    )

    edge_b = subtract3(
        third,
        first,
    )

    return normalized(
        cross3(
            edge_a,
            edge_b,
        )
    )


def face_center(
    mesh: SDFSurfaceMesh,
    face,
):
    points = [
        mesh.vertices[
            index
        ].position
        for index
        in face
    ]

    return (
        sum(
            value[0]
            for value
            in points
        )
        / 4.0,

        sum(
            value[1]
            for value
            in points
        )
        / 4.0,

        sum(
            value[2]
            for value
            in points
        )
        / 4.0,
    )


# =========================================================
# Configuration
# =========================================================
