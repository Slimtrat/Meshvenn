from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any

import bpy

from ...core.geometry_contracts import (
    GeometrySurfaceOutput,
    require_geometry_surface_output,
)
from ...core.material_blend import (
    MaterialBlendConfig,
)
from ...core.material_visibility import (
    MeshVisibilityTester,
)
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.projected_material import (
    DEFAULT_FALLBACK_COLOR,
    blend_projected_color,
)
from ...core.uv_bake import (
    SurfaceColorSample,
    UVBakeConfig,
    UVBakeResult,
    UVBakeTriangle,
    UVBakeVertex,
    bake_uv_texture,
)

from . import constants as _dependency_0
from . import config as _dependency_1
from . import diagnostics as _dependency_2
from . import settings as _dependency_3
from . import geometry as _dependency_4
for _dependency in (_dependency_0, _dependency_1, _dependency_2, _dependency_3, _dependency_4,):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

def _vector3_tuple(
    value,
) -> tuple[
    float,
    float,
    float,
]:
    return (
        float(
            value[0]
        ),
        float(
            value[1]
        ),
        float(
            value[2]
        ),
    )


def _vector2_tuple(
    value,
) -> tuple[
    float,
    float,
]:
    return (
        float(
            value[0]
        ),
        float(
            value[1]
        ),
    )


def _corner_normal(
    mesh: bpy.types.Mesh,
    *,
    loop_index: int,
    vertex_index: int,
    polygon_index: int,
) -> tuple[
    float,
    float,
    float,
]:
    # Blender 5.x corner normals.

    try:
        if (
            mesh.corner_normals
            and loop_index
            < len(
                mesh.corner_normals
            )
        ):
            normal = (
                mesh.corner_normals[
                    loop_index
                ].vector
            )

            if (
                normal.length_squared
                > 1e-12
            ):
                return (
                    _vector3_tuple(
                        normal
                    )
                )

    except Exception:
        pass

    # Vertex-normal fallback.

    try:
        normal = (
            mesh.vertex_normals[
                vertex_index
            ].vector
        )

        if (
            normal.length_squared
            > 1e-12
        ):
            return (
                _vector3_tuple(
                    normal
                )
            )

    except Exception:
        pass

    # Polygon-normal fallback.

    try:
        normal = (
            mesh.polygon_normals[
                polygon_index
            ].vector
        )

        if (
            normal.length_squared
            > 1e-12
        ):
            return (
                _vector3_tuple(
                    normal
                )
            )

    except Exception:
        pass

    raise ValueError(
        (
            "Could not resolve a valid "
            "surface normal for loop "
            f"{loop_index}."
        )
    )


def _read_uv(
    uv_layer,
    loop_index: int,
) -> tuple[
    float,
    float,
]:
    """
    Blender 5.x exposes MeshUVLoopLayer.uv.

    data[] remains as a compatibility fallback.
    """

    try:
        value = (
            uv_layer.uv[
                loop_index
            ].vector
        )

        return (
            _vector2_tuple(
                value
            )
        )

    except Exception:
        value = (
            uv_layer.data[
                loop_index
            ].uv
        )

        return (
            _vector2_tuple(
                value
            )
        )


def _build_uv_triangles(
    obj: bpy.types.Object,
    uv_layer,
) -> tuple[
    UVBakeTriangle,
    ...
]:
    mesh = (
        obj.data
    )

    mesh.update()

    mesh.calc_loop_triangles()

    triangles: list[
        UVBakeTriangle
    ] = []

    for loop_triangle in (
        mesh.loop_triangles
    ):
        loop_indices = tuple(
            int(
                index
            )
            for index
            in loop_triangle.loops
        )

        if len(
            loop_indices
        ) != 3:
            continue

        vertices: list[
            UVBakeVertex
        ] = []

        for loop_index in (
            loop_indices
        ):
            loop = (
                mesh.loops[
                    loop_index
                ]
            )

            vertex_index = int(
                loop.vertex_index
            )

            vertex = (
                mesh.vertices[
                    vertex_index
                ]
            )

            vertices.append(
                UVBakeVertex(
                    position=(
                        _vector3_tuple(
                            vertex.co
                        )
                    ),

                    normal=(
                        _corner_normal(
                            mesh,

                            loop_index=(
                                loop_index
                            ),

                            vertex_index=(
                                vertex_index
                            ),

                            polygon_index=int(
                                loop_triangle
                                .polygon_index
                            ),
                        )
                    ),

                    uv=(
                        _read_uv(
                            uv_layer,
                            loop_index,
                        )
                    ),
                )
            )

        triangles.append(
            UVBakeTriangle(
                a=(
                    vertices[0]
                ),

                b=(
                    vertices[1]
                ),

                c=(
                    vertices[2]
                ),

                source_index=int(
                    loop_triangle
                    .polygon_index
                ),
            )
        )

    if not triangles:
        raise ValueError(
            (
                "Mesh triangulation produced "
                "no UV triangles."
            )
        )

    return tuple(
        triangles
    )


# =========================================================
# Projected-color surface sampler
# =========================================================
