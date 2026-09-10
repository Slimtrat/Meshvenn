from __future__ import annotations

import argparse
import math
import shutil
import sys

from array import array
from pathlib import Path

import bpy
from mathutils import Vector


# =========================================================
# CLI
# =========================================================

def parse_args() -> argparse.Namespace:
    argv = sys.argv

    if "--" in argv:
        argv = argv[
            argv.index("--") + 1:
        ]

    else:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Render lightweight static visual previews "
            "for a generated GLB."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--views",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--size",
        type=int,
        default=256,
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--keep-stills",
        action="store_true",
    )

    parser.add_argument(
        "--preserve-material",
        action="store_true",
        help=(
            "Keep materials imported from the GLB instead "
            "of replacing them with the neutral preview "
            "material. Required for material comparisons."
        ),
    )

    return parser.parse_args(
        argv
    )


# =========================================================
# Cleanup
# =========================================================

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

def look_at(
    obj: bpy.types.Object,
    target: Vector,
) -> None:
    direction = (
        target
        - obj.location
    )

    if direction.length == 0.0:
        return

    obj.rotation_euler = (
        direction
        .to_track_quat(
            "-Z",
            "Y",
        )
        .to_euler()
    )


def create_camera(
    *,
    target: Vector,
    model_size: Vector,
) -> bpy.types.Object:
    camera_data = (
        bpy.data.cameras.new(
            "BPT_PreviewCamera"
        )
    )

    camera = (
        bpy.data.objects.new(
            "BPT_PreviewCamera",
            camera_data,
        )
    )

    bpy.context.scene.collection.objects.link(
        camera
    )

    bpy.context.scene.camera = (
        camera
    )

    horizontal_size = max(
        model_size.x,
        model_size.y,
        0.01,
    )

    vertical_size = max(
        model_size.z,
        0.01,
    )

    framing_size = max(
        horizontal_size,
        vertical_size,
    )

    camera_data.type = (
        "ORTHO"
    )

    camera_data.ortho_scale = (
        framing_size
        * 1.35
    )

    camera_data.clip_start = (
        0.001
    )

    camera_data.clip_end = (
        1000.0
    )

    distance = (
        framing_size
        * 3.0
    )

    camera.location = (
        0.0,
        -distance,
        vertical_size * 0.05,
    )

    look_at(
        camera,
        target,
    )

    return camera


# =========================================================
# Lighting
# =========================================================

def create_area_light(
    *,
    name: str,
    location: tuple[
        float,
        float,
        float,
    ],
    energy: float,
    size: float,
) -> None:
    light_data = (
        bpy.data.lights.new(
            name=name,
            type="AREA",
        )
    )

    light_data.energy = (
        energy
    )

    light_data.shape = (
        "DISK"
    )

    light_data.size = (
        size
    )

    light = (
        bpy.data.objects.new(
            name,
            light_data,
        )
    )

    light.location = (
        location
    )

    bpy.context.scene.collection.objects.link(
        light
    )

    look_at(
        light,
        Vector(
            (
                0.0,
                0.0,
                0.0,
            )
        ),
    )


def setup_lighting(
    model_size: Vector,
) -> None:
    radius = max(
        model_size.x,
        model_size.y,
        model_size.z,
        1.0,
    )

    distance = (
        radius
        * 2.5
    )

    light_size = (
        radius
        * 2.0
    )

    create_area_light(
        name="BPT_Key",
        location=(
            distance,
            -distance,
            distance * 1.3,
        ),
        energy=700.0,
        size=light_size,
    )

    create_area_light(
        name="BPT_Fill",
        location=(
            -distance,
            -distance,
            distance * 0.8,
        ),
        energy=350.0,
        size=light_size,
    )


# =========================================================
# Render
# =========================================================

def setup_render(
    *,
    size: int,
    samples: int,
) -> None:
    scene = (
        bpy.context.scene
    )

    scene.render.engine = (
        "CYCLES"
    )

    scene.cycles.device = (
        "CPU"
    )

    scene.cycles.samples = max(
        1,
        samples,
    )

    scene.cycles.use_denoising = (
        False
    )

    scene.render.resolution_x = (
        size
    )

    scene.render.resolution_y = (
        size
    )

    scene.render.resolution_percentage = (
        100
    )

    scene.render.film_transparent = (
        False
    )

    scene.render.image_settings.file_format = (
        "PNG"
    )

    scene.render.image_settings.color_mode = (
        "RGB"
    )

    scene.render.image_settings.color_depth = (
        "8"
    )

    scene.render.use_file_extension = (
        True
    )

    # -----------------------------------------------------
    # Keep display transform stable between implementations.
    # -----------------------------------------------------

    try:
        scene.view_settings.look = (
            "Medium High Contrast"
        )

    except Exception:
        pass

    world = (
        scene.world
    )

    if world is None:
        world = (
            bpy.data.worlds.new(
                "BPT_PreviewWorld"
            )
        )

        scene.world = (
            world
        )

    world.color = (
        0.035,
        0.035,
        0.04,
    )

    print(
        "Preview render engine: CYCLES CPU"
    )

    print(
        (
            "Cycles samples: "
            f"{scene.cycles.samples}"
        )
    )


# =========================================================
# Views
# =========================================================

def view_angles(
    count: int,
) -> list[
    float
]:
    return [
        (
            2.0
            * math.pi
            * index
            / count
        )
        for index
        in range(
            count
        )
    ]


def place_camera(
    camera: bpy.types.Object,
    *,
    target: Vector,
    model_size: Vector,
    angle: float,
) -> None:
    framing_size = max(
        model_size.x,
        model_size.y,
        model_size.z,
        0.01,
    )

    distance = (
        framing_size
        * 3.0
    )

    height = (
        max(
            model_size.z,
            0.01,
        )
        * 0.05
    )

    camera.location = (
        math.sin(
            angle
        )
        * distance,

        -math.cos(
            angle
        )
        * distance,

        height,
    )

    look_at(
        camera,
        target,
    )


def render_views(
    *,
    camera: bpy.types.Object,
    target: Vector,
    model_size: Vector,
    output_dir: Path,
    views: int,
) -> list[
    Path
]:
    scene = (
        bpy.context.scene
    )

    stills_dir = (
        output_dir
        / "stills"
    )

    stills_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    outputs: list[
        Path
    ] = []

    angles = (
        view_angles(
            views
        )
    )

    for (
        index,
        angle,
    ) in enumerate(
        angles
    ):
        degrees = round(
            360.0
            * index
            / views
        )

        output_path = (
            stills_dir
            / f"view_{degrees:03d}.png"
        )

        place_camera(
            camera,
            target=target,
            model_size=model_size,
            angle=angle,
        )

        scene.render.filepath = str(
            output_path.resolve()
        )

        print(
            (
                "Rendering view "
                f"{degrees:03d}"
            )
        )

        bpy.ops.render.render(
            write_still=True
        )

        if not output_path.exists():
            raise RuntimeError(
                (
                    "Render did not produce: "
                    f"{output_path}"
                )
            )

        outputs.append(
            output_path
        )

    return outputs


# =========================================================
# Contact sheet
# =========================================================

def build_contact_sheet(
    image_paths: list[
        Path
    ],
    output_path: Path,
) -> None:
    if not image_paths:
        raise RuntimeError(
            "No stills for contact sheet."
        )

    images: list[
        bpy.types.Image
    ] = []

    try:
        for path in (
            image_paths
        ):
            image = (
                bpy.data.images.load(
                    str(
                        path.resolve()
                    ),
                    check_existing=False,
                )
            )

            image.update()

            images.append(
                image
            )

        tile_width = int(
            images[0].size[0]
        )

        tile_height = int(
            images[0].size[1]
        )

        for image in images:
            if (
                int(
                    image.size[0]
                )
                != tile_width
                or int(
                    image.size[1]
                )
                != tile_height
            ):
                raise RuntimeError(
                    (
                        "Turntable still dimensions "
                        "are inconsistent."
                    )
                )

        columns = min(
            4,
            len(
                images
            ),
        )

        rows = (
            len(
                images
            )
            + columns
            - 1
        ) // columns

        sheet_width = (
            tile_width
            * columns
        )

        sheet_height = (
            tile_height
            * rows
        )

        sheet_pixels = (
            array(
                "f",
                [
                    0.0
                ],
            )
            * (
                sheet_width
                * sheet_height
                * 4
            )
        )

        tile_values = (
            tile_width
            * tile_height
            * 4
        )

        row_values = (
            tile_width
            * 4
        )

        for (
            index,
            image,
        ) in enumerate(
            images
        ):
            pixels = (
                array(
                    "f",
                    [
                        0.0
                    ],
                )
                * tile_values
            )

            image.pixels.foreach_get(
                pixels
            )

            column = (
                index
                % columns
            )

            row = (
                index
                // columns
            )

            destination_tile_row = (
                rows
                - 1
                - row
            )

            for local_y in range(
                tile_height
            ):
                source_start = (
                    local_y
                    * row_values
                )

                source_end = (
                    source_start
                    + row_values
                )

                destination_y = (
                    destination_tile_row
                    * tile_height
                    + local_y
                )

                destination_start = (
                    (
                        destination_y
                        * sheet_width
                        + column
                        * tile_width
                    )
                    * 4
                )

                destination_end = (
                    destination_start
                    + row_values
                )

                sheet_pixels[
                    destination_start:
                    destination_end
                ] = (
                    pixels[
                        source_start:
                        source_end
                    ]
                )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        contact = (
            bpy.data.images.new(
                name=(
                    "BPT_ContactSheet"
                ),
                width=(
                    sheet_width
                ),
                height=(
                    sheet_height
                ),
                alpha=True,
            )
        )

        try:
            contact.pixels.foreach_set(
                sheet_pixels
            )

            contact.filepath_raw = str(
                output_path.resolve()
            )

            contact.file_format = (
                "PNG"
            )

            contact.save()

        finally:
            bpy.data.images.remove(
                contact
            )

    finally:
        for image in (
            images
        ):
            if (
                image.name
                in bpy.data.images
            ):
                bpy.data.images.remove(
                    image
                )


# =========================================================
# Reusable API
# =========================================================

def render_turntable(
    input_path: Path,
    output_dir: Path,
    *,
    views: int,
    size: int,
    samples: int,
    keep_stills: bool,
    preserve_material: bool,
) -> Path:
    """
    Reusable entry point for both:

        visual_preview.yml
        material comparison

    Existing callers get the historical neutral renderer
    when preserve_material=False.

    Material diagnostics use preserve_material=True.
    """

    if not (
        4
        <= views
        <= 16
    ):
        raise ValueError(
            (
                "views must be "
                "between 4 and 16"
            )
        )

    if size < 128:
        raise ValueError(
            "size must be >= 128"
        )

    if samples < 1:
        raise ValueError(
            "samples must be >= 1"
        )

    input_path = (
        input_path.resolve()
    )

    output_dir = (
        output_dir.resolve()
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    clear_scene()

    objects = (
        import_glb(
            input_path
        )
    )

    material_summary = (
        imported_material_summary(
            objects
        )
    )

    print_material_summary(
        material_summary
    )

    if preserve_material:
        validate_preserved_materials(
            objects
        )

        print(
            (
                "Material mode: "
                "PRESERVE IMPORTED"
            )
        )

    else:
        ensure_preview_material(
            objects
        )

        print(
            (
                "Material mode: "
                "NEUTRAL PREVIEW OVERRIDE"
            )
        )

    (
        target,
        model_size,
    ) = (
        center_objects(
            objects
        )
    )

    camera = (
        create_camera(
            target=target,
            model_size=model_size,
        )
    )

    setup_lighting(
        model_size
    )

    setup_render(
        size=size,
        samples=samples,
    )

    stills = (
        render_views(
            camera=camera,
            target=target,
            model_size=model_size,
            output_dir=output_dir,
            views=views,
        )
    )

    contact_path = (
        output_dir
        / "contact_sheet.png"
    )

    build_contact_sheet(
        stills,
        contact_path,
    )

    if not contact_path.exists():
        raise RuntimeError(
            (
                "Contact sheet was "
                "not generated."
            )
        )

    if not keep_stills:
        stills_dir = (
            output_dir
            / "stills"
        )

        if stills_dir.exists():
            shutil.rmtree(
                stills_dir
            )

    return (
        contact_path
    )


# =========================================================
# Main
# =========================================================

def main() -> None:
    args = (
        parse_args()
    )

    contact_path = (
        render_turntable(
            args.input,
            args.output,
            views=(
                args.views
            ),
            size=(
                args.size
            ),
            samples=(
                args.samples
            ),
            keep_stills=(
                args.keep_stills
            ),
            preserve_material=(
                args.preserve_material
            ),
        )
    )

    print(
        (
            "Visual preview generated: "
            f"{contact_path}"
        )
    )


if __name__ == "__main__":
    main()