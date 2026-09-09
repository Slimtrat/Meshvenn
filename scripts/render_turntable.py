from __future__ import annotations

import argparse
import math
import shutil
import sys

from array import array
from pathlib import Path

import bpy

from mathutils import Vector


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

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
            "Render lightweight visual previews "
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
        "--frames",
        type=int,
        default=24,
    )

    parser.add_argument(
        "--size",
        type=int,
        default=384,
    )

    parser.add_argument(
        "--contact-views",
        type=int,
        default=8,
    )

    parser.add_argument(
        "--fps",
        type=int,
        default=24,
    )

    parser.add_argument(
        "--keep-stills",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )


# ---------------------------------------------------------
# Cleanup
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# GLB import
# ---------------------------------------------------------

def import_glb(
    path: Path,
) -> list[bpy.types.Object]:
    path = path.resolve()

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
        for obj in bpy.data.objects
        if obj not in before
    ]

    meshes = [
        obj
        for obj in imported
        if obj.type == "MESH"
    ]

    if not meshes:
        raise RuntimeError(
            "Imported GLB contains no mesh."
        )

    return meshes


# ---------------------------------------------------------
# Bounds
# ---------------------------------------------------------

def combined_bounds(
    objects: list[bpy.types.Object],
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

        for corner in obj.bound_box:
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
    objects: list[bpy.types.Object],
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


# ---------------------------------------------------------
# Material
# ---------------------------------------------------------

def ensure_preview_material(
    objects: list[bpy.types.Object],
) -> None:
    material = (
        bpy.data.materials.new(
            "BPT_PreviewMaterial"
        )
    )

    material.diffuse_color = (
        0.52,
        0.56,
        0.62,
        1.0,
    )

    material.roughness = (
        0.72
    )

    material.metallic = (
        0.0
    )

    for obj in objects:
        if obj.type != "MESH":
            continue

        if not obj.data.materials:
            obj.data.materials.append(
                material
            )


# ---------------------------------------------------------
# Camera
# ---------------------------------------------------------

def create_orbit_camera(
    *,
    target: Vector,
    model_size: Vector,
) -> tuple[
    bpy.types.Object,
    bpy.types.Object,
]:
    orbit = (
        bpy.data.objects.new(
            "BPT_TurntableOrbit",
            None,
        )
    )

    bpy.context.scene.collection.objects.link(
        orbit
    )

    camera_data = (
        bpy.data.cameras.new(
            "BPT_TurntableCamera"
        )
    )

    camera = (
        bpy.data.objects.new(
            "BPT_TurntableCamera",
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

    distance = (
        framing_size
        * 3.0
    )

    height = (
        vertical_size
        * 0.08
    )

    camera.parent = (
        orbit
    )

    camera.location = (
        0.0,
        -distance,
        height,
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

    camera_data.clip_end = max(
        100.0,
        distance * 10.0,
    )

    direction = (
        target
        - camera.location
    )

    camera.rotation_euler = (
        direction
        .to_track_quat(
            "-Z",
            "Y",
        )
        .to_euler()
    )

    return (
        camera,
        orbit,
    )


# ---------------------------------------------------------
# Lighting
# ---------------------------------------------------------

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
) -> bpy.types.Object:
    data = (
        bpy.data.lights.new(
            name=name,
            type="AREA",
        )
    )

    data.energy = (
        energy
    )

    data.shape = (
        "DISK"
    )

    data.size = (
        size
    )

    light = (
        bpy.data.objects.new(
            name,
            data,
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

    return light


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
        * 1.5
    )

    create_area_light(
        name="BPT_Key",
        location=(
            distance,
            -distance,
            distance * 1.4,
        ),
        energy=900.0,
        size=light_size,
    )

    create_area_light(
        name="BPT_Fill",
        location=(
            -distance,
            -distance * 0.5,
            distance,
        ),
        energy=450.0,
        size=light_size,
    )

    create_area_light(
        name="BPT_Rim",
        location=(
            0.0,
            distance,
            distance * 1.2,
        ),
        energy=650.0,
        size=light_size,
    )


# ---------------------------------------------------------
# Render setup
# ---------------------------------------------------------

def setup_render(
    *,
    size: int,
) -> None:
    scene = (
        bpy.context.scene
    )

    available_engines = {
        item.identifier
        for item in (
            scene
            .bl_rna
            .properties["engine"]
            .enum_items
        )
    }

    if "BLENDER_EEVEE" in available_engines:
        scene.render.engine = (
            "BLENDER_EEVEE"
        )

    elif "CYCLES" in available_engines:
        scene.render.engine = (
            "CYCLES"
        )

        scene.cycles.device = (
            "CPU"
        )

    else:
        raise RuntimeError(
            (
                "No supported Blender "
                "render engine available."
            )
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

    scene.render.image_settings.color_mode = (
        "RGBA"
    )

    scene.render.image_settings.color_depth = (
        "8"
    )

    scene.render.use_file_extension = (
        True
    )

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

    world.use_nodes = (
        True
    )

    background = (
        world.node_tree.nodes.get(
            "Background"
        )
    )

    if background is not None:
        background.inputs[
            "Color"
        ].default_value = (
            0.025,
            0.025,
            0.03,
            1.0,
        )

        background.inputs[
            "Strength"
        ].default_value = (
            0.25
        )


# ---------------------------------------------------------
# Still render
# ---------------------------------------------------------

def render_still(
    *,
    orbit: bpy.types.Object,
    angle: float,
    output_path: Path,
) -> None:
    scene = (
        bpy.context.scene
    )

    orbit.rotation_euler.z = (
        angle
    )

    scene.render.image_settings.file_format = (
        "PNG"
    )

    scene.render.filepath = str(
        output_path.resolve()
    )

    bpy.ops.render.render(
        write_still=True
    )


# ---------------------------------------------------------
# Contact sheet
# ---------------------------------------------------------

def build_contact_sheet(
    image_paths: list[Path],
    output_path: Path,
    *,
    columns: int,
) -> None:
    if not image_paths:
        raise RuntimeError(
            "No images for contact sheet."
        )

    images: list[
        bpy.types.Image
    ] = []

    try:
        for path in image_paths:
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

        rows = (
            len(images)
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
                [0.0],
            )
            * (
                sheet_width
                * sheet_height
                * 4
            )
        )

        row_values = (
            tile_width
            * 4
        )

        image_values = (
            tile_width
            * tile_height
            * 4
        )

        for index, image in enumerate(
            images
        ):
            if (
                int(image.size[0])
                != tile_width
                or int(image.size[1])
                != tile_height
            ):
                raise RuntimeError(
                    (
                        "Contact sheet source "
                        "dimensions do not match."
                    )
                )

            pixels = (
                array(
                    "f",
                    [0.0],
                )
                * image_values
            )

            image.pixels.foreach_get(
                pixels
            )

            column = (
                index
                % columns
            )

            visual_row = (
                index
                // columns
            )

            destination_tile_row = (
                rows
                - 1
                - visual_row
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
                ] = pixels[
                    source_start:
                    source_end
                ]

        contact = (
            bpy.data.images.new(
                name="BPT_ContactSheet",
                width=sheet_width,
                height=sheet_height,
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
        for image in images:
            if image.name in bpy.data.images:
                bpy.data.images.remove(
                    image
                )


def render_contact_sheet(
    *,
    orbit: bpy.types.Object,
    output_dir: Path,
    views: int,
) -> Path:
    stills_dir = (
        output_dir
        / "stills"
    )

    stills_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    image_paths: list[
        Path
    ] = []

    for index in range(
        views
    ):
        angle = (
            2.0
            * math.pi
            * index
            / views
        )

        degrees = round(
            360.0
            * index
            / views
        )

        output_path = (
            stills_dir
            / f"view_{degrees:03d}.png"
        )

        render_still(
            orbit=orbit,
            angle=angle,
            output_path=output_path,
        )

        image_paths.append(
            output_path
        )

    contact_path = (
        output_dir
        / "contact_sheet.png"
    )

    columns = min(
        4,
        views,
    )

    build_contact_sheet(
        image_paths,
        contact_path,
        columns=columns,
    )

    return contact_path


# ---------------------------------------------------------
# Video
# ---------------------------------------------------------

def configure_orbit_animation(
    orbit: bpy.types.Object,
    *,
    frames: int,
) -> None:
    scene = (
        bpy.context.scene
    )

    scene.frame_start = (
        1
    )

    scene.frame_end = (
        frames
    )

    orbit.rotation_mode = (
        "XYZ"
    )

    for frame in (
        1,
        frames + 1,
    ):
        progress = (
            frame - 1
        ) / frames

        orbit.rotation_euler.z = (
            progress
            * 2.0
            * math.pi
        )

        orbit.keyframe_insert(
            data_path="rotation_euler",
            index=2,
            frame=frame,
        )

    if orbit.animation_data is None:
        return

    action = (
        orbit.animation_data.action
    )

    if action is None:
        return

    for curve in action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = (
                "LINEAR"
            )


def render_video(
    *,
    orbit: bpy.types.Object,
    output_dir: Path,
    frames: int,
    fps: int,
) -> Path:
    scene = (
        bpy.context.scene
    )

    configure_orbit_animation(
        orbit,
        frames=frames,
    )

    scene.render.fps = (
        fps
    )

    scene.render.image_settings.file_format = (
        "FFMPEG"
    )

    scene.render.ffmpeg.format = (
        "MPEG4"
    )

    scene.render.ffmpeg.codec = (
        "H264"
    )

    scene.render.ffmpeg.constant_rate_factor = (
        "MEDIUM"
    )

    scene.render.ffmpeg.audio_codec = (
        "NONE"
    )

    video_stem = (
        output_dir
        / "turntable"
    )

    scene.render.filepath = str(
        video_stem.resolve()
    )

    bpy.ops.render.render(
        animation=True
    )

    expected = (
        output_dir
        / "turntable.mp4"
    )

    if expected.exists():
        return expected

    candidates = sorted(
        output_dir.glob(
            "turntable*.mp4"
        )
    )

    if not candidates:
        raise RuntimeError(
            (
                "Blender did not generate "
                "the expected MP4."
            )
        )

    if candidates[0] != expected:
        candidates[0].replace(
            expected
        )

    return expected


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.frames < 8:
        raise ValueError(
            "frames must be >= 8"
        )

    if args.size < 128:
        raise ValueError(
            "size must be >= 128"
        )

    if not (
        4
        <= args.contact_views
        <= 16
    ):
        raise ValueError(
            (
                "contact-views must be "
                "between 4 and 16"
            )
        )

    if args.fps <= 0:
        raise ValueError(
            "fps must be > 0"
        )

    input_path = (
        args.input.resolve()
    )

    output_dir = (
        args.output.resolve()
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    clear_scene()

    objects = import_glb(
        input_path
    )

    (
        target,
        model_size,
    ) = center_objects(
        objects
    )

    ensure_preview_material(
        objects
    )

    (
        _camera,
        orbit,
    ) = create_orbit_camera(
        target=target,
        model_size=model_size,
    )

    setup_lighting(
        model_size
    )

    setup_render(
        size=args.size
    )

    contact_path = (
        render_contact_sheet(
            orbit=orbit,
            output_dir=output_dir,
            views=args.contact_views,
        )
    )

    video_path = (
        render_video(
            orbit=orbit,
            output_dir=output_dir,
            frames=args.frames,
            fps=args.fps,
        )
    )

    if not args.keep_stills:
        stills_dir = (
            output_dir
            / "stills"
        )

        if stills_dir.exists():
            shutil.rmtree(
                stills_dir
            )

    if not contact_path.exists():
        raise RuntimeError(
            "Contact sheet was not generated."
        )

    if not video_path.exists():
        raise RuntimeError(
            "Turntable MP4 was not generated."
        )

    print(
        "Visual preview generated."
    )

    print(
        f"Contact sheet: {contact_path}"
    )

    print(
        f"Turntable: {video_path}"
    )


if __name__ == "__main__":
    main()