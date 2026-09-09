from __future__ import annotations

from array import array

import bpy

from .native_bridge import NativeMesh


def create_blender_mesh_from_native(
    native_mesh: NativeMesh,
    *,
    mesh_name: str = "ProjectionToolNativeMesh",
    object_name: str = "ProjectionToolNativeScan",
) -> bpy.types.Object:
    _validate_native_mesh(
        native_mesh
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

        collection = (
            bpy.context.collection
            or bpy.context.scene.collection
        )

        collection.objects.link(
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

    _validate_native_mesh(
        native_mesh
    )

    _set_geometry(
        obj.data,
        native_mesh,
    )

    _make_active(
        obj
    )


def _validate_native_mesh(
    native_mesh: NativeMesh,
) -> None:
    if native_mesh.vertex_count <= 0:
        raise ValueError(
            "Native mesh contains no vertices."
        )

    if (
        len(native_mesh.vertices)
        % 3
        != 0
    ):
        raise ValueError(
            (
                "Native vertex buffer length "
                "must be divisible by 3."
            )
        )

    polygon_count = (
        native_mesh.polygon_count
    )

    if (
        len(
            native_mesh.polygon_starts
        )
        != polygon_count
    ):
        raise ValueError(
            (
                "Native mesh polygon metadata "
                "mismatch."
            )
        )

    if polygon_count == 0:
        if native_mesh.index_count != 0:
            raise ValueError(
                (
                    "Native mesh contains loops "
                    "without polygons."
                )
            )

        return

    last_polygon = (
        polygon_count
        - 1
    )

    expected_loop_count = (
        int(
            native_mesh.polygon_starts[
                last_polygon
            ]
        )
        + int(
            native_mesh.polygon_sizes[
                last_polygon
            ]
        )
    )

    if (
        expected_loop_count
        != native_mesh.index_count
    ):
        raise ValueError(
            (
                "Native mesh loop metadata "
                "does not match index buffer."
            )
        )


def _set_geometry(
    mesh: bpy.types.Mesh,
    native_mesh: NativeMesh,
) -> None:
    vertices = (
        native_mesh.vertices
    )

    indices = (
        native_mesh.indices
    )

    polygon_starts = (
        native_mesh.polygon_starts
    )

    polygon_sizes = (
        native_mesh.polygon_sizes
    )

    vertex_count = (
        native_mesh.vertex_count
    )

    loop_count = (
        native_mesh.index_count
    )

    polygon_count = (
        native_mesh.polygon_count
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

    if loop_count:
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

    if polygon_count:
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

    polygon_count = len(
        obj.data.polygons
    )

    if polygon_count == 0:
        return

    smooth_values = (
        array(
            "b",
            [1],
        )
        * polygon_count
    )

    obj.data.polygons.foreach_set(
        "use_smooth",
        smooth_values,
    )

    obj.data.update()


def _make_active(
    obj: bpy.types.Object,
) -> None:
    view_layer = (
        bpy.context.view_layer
    )

    if view_layer is None:
        return

    active = (
        view_layer.objects.active
    )

    if (
        active is not None
        and active != obj
    ):
        active.select_set(
            False
        )

    obj.select_set(
        True
    )

    view_layer.objects.active = (
        obj
    )