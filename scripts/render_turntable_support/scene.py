from __future__ import annotations

import argparse
import math
import shutil
import sys
from array import array
from pathlib import Path
import bpy
from mathutils import Vector

def clear_scene() -> None:
    for obj in tuple(
        bpy.data.objects
    ):
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )

    for mesh in tuple(
        bpy.data.meshes
    ):
        if mesh.users == 0:
            bpy.data.meshes.remove(
                mesh
            )

    for material in tuple(
        bpy.data.materials
    ):
        if material.users == 0:
            bpy.data.materials.remove(
                material
            )

    for image in tuple(
        bpy.data.images
    ):
        if image.users == 0:
            bpy.data.images.remove(
                image
            )

    for camera in tuple(
        bpy.data.cameras
    ):
        if camera.users == 0:
            bpy.data.cameras.remove(
                camera
            )

    for light in tuple(
        bpy.data.lights
    ):
        if light.users == 0:
            bpy.data.lights.remove(
                light
            )


# =========================================================
# GLB import
# =========================================================

def import_glb(
    path: Path,
) -> list[
    bpy.types.Object
]:
    path = (
        path.resolve()
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Missing GLB: {path}"
        )

    before = set(
        bpy.data.objects
    )

    bpy.ops.import_scene.gltf(
        filepath=str(
            path
        )
    )

    imported = [
        obj
        for obj
        in bpy.data.objects
        if obj not in before
    ]

    meshes = [
        obj
        for obj
        in imported
        if obj.type == "MESH"
    ]

    if not meshes:
        raise RuntimeError(
            (
                "Imported GLB contains "
                "no mesh."
            )
        )

    return meshes


# =========================================================
# Imported material diagnostics
# =========================================================

def imported_material_summary(
    objects: list[
        bpy.types.Object
    ],
) -> dict:
    materials = []

    images = []

    color_attributes = []

    uv_layers = []

    for obj in objects:
        if obj.type != "MESH":
            continue

        mesh = obj.data

        for material in (
            mesh.materials
        ):
            if (
                material is not None
                and material.name
                not in materials
            ):
                materials.append(
                    material.name
                )

                node_tree = (
                    material.node_tree
                )

                if node_tree is not None:
                    for node in (
                        node_tree.nodes
                    ):
                        image = getattr(
                            node,
                            "image",
                            None,
                        )

                        if (
                            image is not None
                            and image.name
                            not in images
                        ):
                            images.append(
                                image.name
                            )

        for attribute in (
            mesh.color_attributes
        ):
            if (
                attribute.name
                not in color_attributes
            ):
                color_attributes.append(
                    attribute.name
                )

        for uv_layer in (
            mesh.uv_layers
        ):
            if (
                uv_layer.name
                not in uv_layers
            ):
                uv_layers.append(
                    uv_layer.name
                )

    return {
        "materials": (
            materials
        ),

        "images": (
            images
        ),

        "color_attributes": (
            color_attributes
        ),

        "uv_layers": (
            uv_layers
        ),
    }


def print_material_summary(
    summary: dict,
) -> None:
    print(
        "Imported material state:"
    )

    for name in (
        "materials",
        "images",
        "color_attributes",
        "uv_layers",
    ):
        values = (
            summary.get(
                name,
                []
            )
        )

        print(
            (
                f"  {name}: "
                + (
                    ", ".join(
                        values
                    )
                    if values
                    else "none"
                )
            )
        )


# =========================================================
# Bounds
# =========================================================

def combined_bounds(
    objects: list[
        bpy.types.Object
    ],
) -> tuple[
    Vector,
    Vector,
]:
    min_corner = Vector(
        (
            float("inf"),
            float("inf"),
            float("inf"),
        )
    )

    max_corner = Vector(
        (
            float("-inf"),
            float("-inf"),
            float("-inf"),
        )
    )

    for obj in objects:
        matrix = (
            obj.matrix_world
        )

        for corner in (
            obj.bound_box
        ):
            point = (
                matrix
                @ Vector(
                    corner
                )
            )

            min_corner.x = min(
                min_corner.x,
                point.x,
            )

            min_corner.y = min(
                min_corner.y,
                point.y,
            )

            min_corner.z = min(
                min_corner.z,
                point.z,
            )

            max_corner.x = max(
                max_corner.x,
                point.x,
            )

            max_corner.y = max(
                max_corner.y,
                point.y,
            )

            max_corner.z = max(
                max_corner.z,
                point.z,
            )

    return (
        min_corner,
        max_corner,
    )


def center_objects(
    objects: list[
        bpy.types.Object
    ],
) -> tuple[
    Vector,
    Vector,
]:
    (
        min_corner,
        max_corner,
    ) = combined_bounds(
        objects
    )

    center = (
        min_corner
        + max_corner
    ) * 0.5

    for obj in objects:
        obj.location -= (
            center
        )

    (
        centered_min,
        centered_max,
    ) = combined_bounds(
        objects
    )

    model_size = (
        centered_max
        - centered_min
    )

    return (
        Vector(
            (
                0.0,
                0.0,
                0.0,
            )
        ),
        model_size,
    )


# =========================================================
# Neutral material
#
# Existing visual-preview behavior.
# =========================================================

def ensure_preview_material(
    objects: list[
        bpy.types.Object
    ],
) -> None:
    material = (
        bpy.data.materials.new(
            "BPT_PreviewMaterial"
        )
    )

    material.diffuse_color = (
        0.58,
        0.61,
        0.66,
        1.0,
    )

    material.roughness = (
        0.75
    )

    material.metallic = (
        0.0
    )

    for obj in objects:
        if obj.type != "MESH":
            continue

        obj.data.materials.clear()

        obj.data.materials.append(
            material
        )


# =========================================================
# Material validation
# =========================================================

def validate_preserved_materials(
    objects: list[
        bpy.types.Object
    ],
) -> None:
    """
    A comparison render should never silently become a
    neutral/white mesh because the GLB lost its material.

    Vertex-color and texture implementations both require at
    least one actual Blender material after GLTF import.
    """

    mesh_objects = [
        obj
        for obj
        in objects
        if obj.type == "MESH"
    ]

    if not mesh_objects:
        raise RuntimeError(
            "No mesh object to validate."
        )

    material_count = sum(
        1
        for obj
        in mesh_objects
        for material
        in obj.data.materials
        if material is not None
    )

    if material_count <= 0:
        raise RuntimeError(
            (
                "--preserve-material was requested, "
                "but imported GLB contains no material."
            )
        )


# =========================================================
# Camera
# =========================================================
