# core/cleanup.py

from __future__ import annotations

import bpy


def cleanup_generated_object(
    obj: bpy.types.Object,
    *,
    auto_remesh: bool = True,
    voxel_size: float = 0.05,
    smooth_iterations: int = 3,
) -> None:
    if obj.type != "MESH":
        raise TypeError("Generated object must be a mesh.")

    _make_active(obj)

    _apply_object_scale(obj)

    if auto_remesh:
        _voxel_remesh(
            obj,
            voxel_size=voxel_size,
        )

    if smooth_iterations > 0:
        _smooth_mesh(
            obj,
            iterations=smooth_iterations,
        )

    _merge_by_distance(obj)
    _recalculate_normals(obj)
    _shade_smooth(obj)


def _make_active(
    obj: bpy.types.Object,
) -> None:
    bpy.ops.object.select_all(
        action="DESELECT",
    )

    obj.select_set(True)

    bpy.context.view_layer.objects.active = obj


def _apply_object_scale(
    obj: bpy.types.Object,
) -> None:
    _make_active(obj)

    bpy.ops.object.transform_apply(
        location=False,
        rotation=False,
        scale=True,
    )


def _voxel_remesh(
    obj: bpy.types.Object,
    *,
    voxel_size: float,
) -> None:
    if voxel_size <= 0.0:
        raise ValueError(
            "Voxel size must be greater than zero."
        )

    _make_active(obj)

    obj.data.remesh_voxel_size = voxel_size

    bpy.ops.object.mode_set(
        mode="SCULPT",
    )

    try:
        bpy.ops.object.voxel_remesh()
    finally:
        bpy.ops.object.mode_set(
            mode="OBJECT",
        )


def _smooth_mesh(
    obj: bpy.types.Object,
    *,
    iterations: int,
) -> None:
    if iterations <= 0:
        return

    _make_active(obj)

    modifier = obj.modifiers.new(
        name="Projection Tool Smooth",
        type="SMOOTH",
    )

    modifier.factor = 0.5
    modifier.iterations = iterations

    bpy.ops.object.modifier_apply(
        modifier=modifier.name,
    )


def _merge_by_distance(
    obj: bpy.types.Object,
) -> None:
    _make_active(obj)

    bpy.ops.object.mode_set(
        mode="EDIT",
    )

    try:
        bpy.ops.mesh.select_all(
            action="SELECT",
        )

        bpy.ops.mesh.remove_doubles(
            threshold=0.0001,
        )
    finally:
        bpy.ops.object.mode_set(
            mode="OBJECT",
        )


def _recalculate_normals(
    obj: bpy.types.Object,
) -> None:
    _make_active(obj)

    bpy.ops.object.mode_set(
        mode="EDIT",
    )

    try:
        bpy.ops.mesh.select_all(
            action="SELECT",
        )

        bpy.ops.mesh.normals_make_consistent(
            inside=False,
        )
    finally:
        bpy.ops.object.mode_set(
            mode="OBJECT",
        )


def _shade_smooth(
    obj: bpy.types.Object,
) -> None:
    _make_active(obj)

    for polygon in obj.data.polygons:
        polygon.use_smooth = True

    obj.data.update()