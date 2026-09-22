from __future__ import annotations

from .shared import Matrix, Path, bpy

def clear_scene() -> None:
    for obj in tuple(
        bpy.data.objects
    ):
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )

def scale_object_to_height(
    obj: bpy.types.Object,
    target_height: float,
) -> None:
    if target_height <= 0.0:
        raise ValueError(
            (
                "Target height must be "
                "greater than zero."
            )
        )

    current_height = float(
        obj.dimensions.z
    )

    if current_height <= 0.0:
        return

    scale = (
        target_height
        / current_height
    )

    obj.data.transform(
        Matrix.Scale(
            scale,
            4,
        )
    )

    obj.data.update()

def _select_only(
    obj: bpy.types.Object,
) -> None:
    for selected in tuple(
        bpy.context.selected_objects
    ):
        selected.select_set(
            False
        )

    obj.select_set(
        True
    )

    bpy.context.view_layer.objects.active = (
        obj
    )

def export_object(
    obj: bpy.types.Object,
    *,
    output_dir: Path,
    stem: str,
    save_blend: bool,
) -> dict:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    glb_path = (
        output_dir
        / f"{stem}.glb"
    )

    blend_path = (
        output_dir
        / f"{stem}.blend"
    )

    _select_only(
        obj
    )

    bpy.ops.export_scene.gltf(
        filepath=str(
            glb_path.resolve()
        ),
        export_format="GLB",
        use_selection=True,
    )

    if save_blend:
        bpy.ops.wm.save_as_mainfile(
            filepath=str(
                blend_path.resolve()
            )
        )

    return {
        "glb": str(
            glb_path
        ),
        "blend": (
            str(
                blend_path
            )
            if save_blend
            else None
        ),
        "vertices": len(
            obj.data.vertices
        ),
        "faces": len(
            obj.data.polygons
        ),
        "dimensions": [
            float(value)
            for value
            in obj.dimensions
        ],
        "materials": [
            material.name
            for material
            in obj.data.materials
            if material is not None
        ],
        "color_attributes": [
            attribute.name
            for attribute
            in obj.data.color_attributes
        ],
    }
