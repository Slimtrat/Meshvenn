from __future__ import annotations

import bpy

from .native_bridge import NativeMesh


def create_blender_mesh_from_native(
    native_mesh: NativeMesh,
    *,
    mesh_name: str = "ProjectionToolNativeMesh",
    object_name: str = "ProjectionToolNativeScan",
) -> bpy.types.Object:
    if native_mesh.vertex_count == 0:
        raise ValueError(
            "Native mesh contains no vertices."
        )

    mesh = bpy.data.meshes.new(
        mesh_name
    )

    try:
        _set_geometry(
            mesh,
            native_mesh,
        )

        obj = bpy.data.objects.new(
            object_name,
            mesh,
        )

        bpy.context.scene.collection.objects.link(
            obj
        )

        _make_active(
            obj
        )

        return obj

    except Exception:
        bpy.data.meshes.remove(
            mesh
        )
        raise


def update_blender_mesh_from_native(
    obj: bpy.types.Object,
    native_mesh: NativeMesh,
) -> None:
    if obj.type != "MESH":
        raise TypeError(
            "Target object must be a mesh."
        )

    if native_mesh.vertex_count == 0:
        raise ValueError(
            "Native mesh contains no vertices."
        )

    _set_geometry(
        obj.data,
        native_mesh,
    )

    _make_active(
        obj
    )


def _set_geometry(
    mesh: bpy.types.Mesh,
    native_mesh: NativeMesh,
) -> None:
    vertices = native_mesh.vertices
    indices = native_mesh.indices
    polygon_starts = (
        native_mesh.polygon_starts
    )
    polygon_sizes = (
        native_mesh.polygon_sizes
    )

    vertex_count = (
        len(vertices) // 3
    )

    loop_count = len(
        indices
    )

    polygon_count = len(
        polygon_sizes
    )

    if (
        len(polygon_starts)
        != polygon_count
    ):
        raise ValueError(
            "Native mesh polygon metadata mismatch."
        )

    if sum(
        polygon_sizes
    ) != loop_count:
        raise ValueError(
            "Native mesh loop count mismatch."
        )

    mesh.clear_geometry()

    # -----------------------------------------------------
    # Vertices
    # -----------------------------------------------------

    mesh.vertices.add(
        vertex_count
    )

    mesh.vertices.foreach_set(
        "co",
        vertices,
    )

    # -----------------------------------------------------
    # Loops
    # -----------------------------------------------------

    mesh.loops.add(
        loop_count
    )

    mesh.loops.foreach_set(
        "vertex_index",
        indices,
    )

    # -----------------------------------------------------
    # Polygons
    # -----------------------------------------------------

    mesh.polygons.add(
        polygon_count
    )

    mesh.polygons.foreach_set(
        "loop_start",
        polygon_starts,
    )

    mesh.polygons.foreach_set(
        "loop_total",
        polygon_sizes,
    )

    # -----------------------------------------------------
    # Finalize
    # -----------------------------------------------------

    mesh.update(
        calc_edges=True
    )

    mesh.validate(
        verbose=False,
        clean_customdata=False,
    )


def shade_smooth_native_object(
    obj: bpy.types.Object,
) -> None:
    if obj.type != "MESH":
        raise TypeError(
            "Object must be a mesh."
        )

    polygons = obj.data.polygons

    if not polygons:
        return

    smooth_values = [
        True
        for _ in range(
            len(polygons)
        )
    ]

    polygons.foreach_set(
        "use_smooth",
        smooth_values,
    )

    obj.data.update()


def _make_active(
    obj: bpy.types.Object,
) -> None:
    bpy.ops.object.select_all(
        action="DESELECT"
    )

    obj.select_set(
        True
    )

    bpy.context.view_layer.objects.active = (
        obj
    )