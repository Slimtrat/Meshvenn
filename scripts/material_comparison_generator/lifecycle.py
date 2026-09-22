from __future__ import annotations

import bpy


# =========================================================
# Blender lifecycle
# =========================================================

def cleanup_object(
    obj: bpy.types.Object | None,
) -> None:
    if obj is None:
        return

    mesh = (
        obj.data
        if (
            obj.type == "MESH"
        )
        else None
    )

    materials = []

    images = []

    if mesh is not None:
        materials = [
            material
            for material
            in mesh.materials
            if material is not None
        ]

    for material in materials:
        node_tree = (
            material.node_tree
        )

        if node_tree is None:
            continue

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
                and image not in images
            ):
                images.append(
                    image
                )

    if (
        obj.name
        in bpy.data.objects
    ):
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )

    if (
        mesh is not None
        and mesh.users == 0
        and mesh.name
        in bpy.data.meshes
    ):
        bpy.data.meshes.remove(
            mesh
        )

    for material in materials:
        if (
            material.users == 0
            and material.name
            in bpy.data.materials
        ):
            bpy.data.materials.remove(
                material
            )

    for image in images:
        if (
            image.users == 0
            and image.name
            in bpy.data.images
        ):
            bpy.data.images.remove(
                image
            )
