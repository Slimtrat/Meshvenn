from __future__ import annotations

import importlib
import math
from pathlib import Path
from typing import Any

import bpy

from .constants import *
from .support import (_clamp01, _purge_package_modules, _quantize_unorm8, _require, _require_close, _require_rgba8_close, _section)

# =========================================================
# Cleanup
# =========================================================

def _remove_named_object(
    name: str,
) -> None:
    obj = bpy.data.objects.get(
        name
    )

    if obj is not None:
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )


def _remove_named_mesh(
    name: str,
) -> None:
    mesh = bpy.data.meshes.get(
        name
    )

    if mesh is not None:
        bpy.data.meshes.remove(
            mesh,
            do_unlink=True,
        )


def _cleanup_datablock(
    datablock: Any,
) -> None:
    if datablock is None:
        return

    try:
        if isinstance(
            datablock,
            bpy.types.Material,
        ):
            bpy.data.materials.remove(
                datablock,
                do_unlink=True,
            )

            return

        if isinstance(
            datablock,
            bpy.types.Image,
        ):
            bpy.data.images.remove(
                datablock,
                do_unlink=True,
            )

            return

        if isinstance(
            datablock,
            bpy.types.Object,
        ):
            bpy.data.objects.remove(
                datablock,
                do_unlink=True,
            )

            return

        if isinstance(
            datablock,
            bpy.types.Mesh,
        ):
            bpy.data.meshes.remove(
                datablock,
                do_unlink=True,
            )

    except Exception:
        print(
            (
                "Cleanup warning for "
                f"{type(datablock).__name__}:"
            )
        )

        traceback.print_exc()


# =========================================================
# Blender UV compatibility
# =========================================================

def _set_loop_uv(
    uv_layer,
    loop_index: int,
    uv: tuple[
        float,
        float,
    ],
) -> None:
    """
    Blender 5.x:

        uv_layer.uv[index].vector

    Older fallback:

        uv_layer.data[index].uv
    """

    try:
        uv_layer.uv[
            loop_index
        ].vector = uv

        return

    except Exception:
        pass

    uv_layer.data[
        loop_index
    ].uv = uv


# =========================================================
# Test mesh
# =========================================================

def _create_test_mesh(
) -> tuple[
    bpy.types.Object,
    bpy.types.Mesh,
    Any,
]:
    _section(
        "create Blender mesh"
    )

    _remove_named_object(
        OBJECT_NAME
    )

    _remove_named_mesh(
        MESH_NAME
    )

    mesh = (
        bpy.data.meshes.new(
            MESH_NAME
        )
    )

    # -----------------------------------------------------
    # Geometry deliberately matches UV coordinates:
    #
    #     X == U
    #     Y == V
    #
    #
    #        3 -------- 2
    #        |        / |
    #        |      /   |
    #        |    /     |
    #        |  /       |
    #        |/         |
    #        0 -------- 1
    #
    # -----------------------------------------------------

    vertices = (
        (
            0.0,
            0.0,
            0.0,
        ),
        (
            1.0,
            0.0,
            0.0,
        ),
        (
            1.0,
            1.0,
            0.0,
        ),
        (
            0.0,
            1.0,
            0.0,
        ),
    )

    faces = (
        (
            0,
            1,
            2,
        ),
        (
            0,
            2,
            3,
        ),
    )

    mesh.from_pydata(
        vertices,
        (),
        faces,
    )

    mesh.update()

    obj = (
        bpy.data.objects.new(
            OBJECT_NAME,
            mesh,
        )
    )

    bpy.context.scene.collection.objects.link(
        obj
    )

    uv_layer = (
        mesh.uv_layers.new(
            name=(
                UV_LAYER_NAME
            ),
            do_init=False,
        )
    )

    for loop in mesh.loops:
        vertex = (
            mesh.vertices[
                loop.vertex_index
            ]
        )

        _set_loop_uv(
            uv_layer,
            loop.index,
            (
                float(
                    vertex.co.x
                ),
                float(
                    vertex.co.y
                ),
            ),
        )

    mesh.uv_layers.active = (
        uv_layer
    )

    try:
        uv_layer.active_render = True

    except Exception:
        pass

    mesh.update()

    _require(
        len(
            mesh.vertices
        )
        == 4,
        (
            "Test mesh must contain "
            "4 vertices."
        ),
    )

    _require(
        len(
            mesh.polygons
        )
        == 2,
        (
            "Test mesh must contain "
            "2 polygons."
        ),
    )

    _require(
        len(
            mesh.loops
        )
        == 6,
        (
            "Test mesh must contain "
            "6 loops."
        ),
    )

    print(
        "Mesh: OK"
    )

    print(
        (
            "  vertices: "
            f"{len(mesh.vertices)}"
        )
    )

    print(
        (
            "  polygons: "
            f"{len(mesh.polygons)}"
        )
    )

    print(
        (
            "  loops:    "
            f"{len(mesh.loops)}"
        )
    )

    return (
        obj,
        mesh,
        uv_layer,
    )
