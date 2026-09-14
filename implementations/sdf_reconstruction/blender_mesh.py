from __future__ import annotations

from array import array

import bpy

from ...core.geometry_contracts import GeometryProjectionSpace
from ...core.sdf_surface import SDFSurfaceResult
from .config import DEFAULT_MESH_NAME, DEFAULT_OBJECT_NAME, SDFReconstructionConfig

# =========================================================
# Projection space
# =========================================================

def _projection_space_from_config(
    config: SDFReconstructionConfig,
) -> GeometryProjectionSpace:
    """
    MATERIAL currently expects the historical
    surface-envelope-v1 convention.

    SDF itself works in normalized [-1,+1] coordinates.

    We therefore expose an envelope whose inverse mapping
    reproduces exactly those normalized coordinates.
    """

    return GeometryProjectionSpace(
        width=(
            config.resolution
        ),

        depth=(
            config.resolution
        ),

        height=(
            config.resolution
        ),

        voxel_size=(
            config.voxel_size
        ),

        center_xy=(
            config.center_xy
        ),
    )


def _normalized_to_local(
    position: tuple[
        float,
        float,
        float,
    ],
    projection_space: GeometryProjectionSpace,
) -> tuple[
    float,
    float,
    float,
]:
    """
    Convert SDF normalized coordinates into the exact local
    surface-envelope convention consumed by MATERIAL.

    This is the inverse of:

        surface_position_to_normalized()

    for GeometryProjectionSpace.SURFACE_ENVELOPE_V1.
    """

    (
        nx,
        ny,
        nz,
    ) = position

    nx = float(
        nx
    )

    ny = float(
        ny
    )

    nz = float(
        nz
    )

    physical_width = (
        projection_space
        .physical_width
    )

    physical_depth = (
        projection_space
        .physical_depth
    )

    physical_height = (
        projection_space
        .physical_height
    )

    if projection_space.center_xy:
        x = (
            nx
            * physical_width
            * 0.5
        )

        y = (
            ny
            * physical_depth
            * 0.5
        )

    else:
        x = (
            (
                nx
                + 1.0
            )
            * physical_width
            * 0.5
        )

        y = (
            (
                ny
                + 1.0
            )
            * physical_depth
            * 0.5
        )

    z = (
        (
            nz
            + 1.0
        )
        * physical_height
        * 0.5
    )

    return (
        x,
        y,
        z,
    )


# =========================================================
# Blender mesh creation
# =========================================================

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
        try:
            active.select_set(
                False
            )

        except Exception:
            pass

    obj.select_set(
        True
    )

    view_layer.objects.active = (
        obj
    )


def _shade_smooth(
    obj: bpy.types.Object,
) -> None:
    if obj.type != "MESH":
        raise TypeError(
            (
                "SDF surface object "
                "must be a mesh."
            )
        )

    polygon_count = len(
        obj.data.polygons
    )

    if polygon_count <= 0:
        return

    smooth_values = (
        array(
            "b",
            [
                1
            ],
        )
        * polygon_count
    )

    obj.data.polygons.foreach_set(
        "use_smooth",
        smooth_values,
    )

    obj.data.update()


def _create_blender_surface(
    surface_result: SDFSurfaceResult,
    projection_space: GeometryProjectionSpace,
    *,
    mesh_name: str = DEFAULT_MESH_NAME,
    object_name: str = DEFAULT_OBJECT_NAME,
) -> bpy.types.Object:
    """
    Inject the algorithm-neutral SDF surface into Blender.

    Crucially, we do NOT keep vertices in normalized
    [-1,+1] coordinates.

    MATERIAL expects mesh-local coordinates following
    GeometryProjectionSpace, so each normalized SDF vertex
    is converted to surface-envelope local space first.
    """

    surface = (
        surface_result.mesh
    )

    if surface.vertex_count <= 0:
        raise ValueError(
            (
                "SDF surface contains "
                "no vertices."
            )
        )

    if surface.polygon_count <= 0:
        raise ValueError(
            (
                "SDF surface contains "
                "no polygons."
            )
        )

    vertices = [
        _normalized_to_local(
            vertex.position,
            projection_space,
        )
        for vertex
        in surface.vertices
    ]

    faces = [
        tuple(
            int(
                index
            )
            for index
            in face
        )
        for face
        in surface.faces
    ]

    mesh = (
        bpy.data.meshes.new(
            mesh_name
        )
    )

    obj = None

    try:
        mesh.from_pydata(
            vertices,
            [],
            faces,
        )

        mesh.update(
            calc_edges=True
        )

        mesh.validate(
            verbose=False,
            clean_customdata=False,
        )

        if len(
            mesh.vertices
        ) <= 0:
            raise RuntimeError(
                (
                    "Blender SDF mesh contains "
                    "no vertices after injection."
                )
            )

        if len(
            mesh.polygons
        ) <= 0:
            raise RuntimeError(
                (
                    "Blender SDF mesh contains "
                    "no polygons after injection."
                )
            )

        obj = (
            bpy.data.objects.new(
                object_name,
                mesh,
            )
        )

        collection = (
            bpy.context.collection
            or bpy.context.scene.collection
        )

        collection.objects.link(
            obj
        )

        _shade_smooth(
            obj
        )

        _make_active(
            obj
        )

        return obj

    except Exception:
        if obj is not None:
            try:
                bpy.data.objects.remove(
                    obj,
                    do_unlink=True,
                )

            except Exception:
                pass

        if mesh.users == 0:
            try:
                bpy.data.meshes.remove(
                    mesh
                )

            except Exception:
                pass

        raise


def _remove_blender_object(
    obj: (
        bpy.types.Object
        | None
    ),
) -> None:
    if obj is None:
        return

    mesh = (
        obj.data
        if (
            obj.type == "MESH"
            and obj.data is not None
        )
        else None
    )

    try:
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )

    finally:
        if (
            mesh is not None
            and mesh.users == 0
        ):
            bpy.data.meshes.remove(
                mesh
            )
