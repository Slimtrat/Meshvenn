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
# Scene cleanup
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
# GLB
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

    size = (
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
        size,
    )


# ---------------------------------------------------------
# Materials
# ---------------------------------------------------------

def ensure_preview_material(
    objects: list[bpy.types.Object],
) -> None:
    preview_material = (
        bpy.data.materials.new(
            "BPT_PreviewMaterial"
        )
    )

    preview_material.diffuse_color = (
        0.55,
        0.58,
        0.62,
        1.0,
    )

    preview_material.roughness = (
        0.7
    )

    preview_material.metallic = (
        0.0
    )

    for obj in objects:
        if obj.type != "MESH":
            continue

        if not obj.data.materials:
            obj.data.materials.append(
                preview_material
            )


# ---------------------------------------------------------
# Camera / orbit
# ---------------------------------------------------------

def look_at(
    obj: bpy.types.Object,
    target: Vector,
) -> None:
    direction = (
        target
        - obj.matrix_world.translation
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


def create_orbit_camera(
    *,
    target: Vector,
    model_size: Vector,
) -> tuple[
    bpy.types.Object,
    bpy.types.Object,
]:
    orbit = bpy.data.objects.new(
        "BPT_TurntableOrbit",
        None,
    )

    bpy.context.scene.collection.objects.link(
        orbit
    )

    camera_data = (
        bpy.data.cameras.new(
            "BPT_TurntableCamera"
        )
    )

    camera = bpy.data.objects.new(
        "BPT_TurntableCamera",
        camera_data,
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

    camera_data.clip_end = (
        max(
            100.0,
            distance * 10.0,
        )
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
# Render configuration
# ---------------------------------------------------------

def setup_workbench(
    *,
    size: int,
) -> None:
    scene = (
        bpy.context.scene
    )

    scene.render.engine = (
        "BLENDER_WORKBENCH"
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

    shading = (
        scene.display.shading
    )

    shading.light = (
        "STUDIO"
    )

    shading.color_type = (
        "MATERIAL"
    )

    shading.show_shadows = (
        True
    )

    shading.show_cavity = (
        True
    )

    shading.cavity_type = (
        "BOTH"
    )

    shading.show_specular_highlight = (
        True
    )

    world = (
        scene.world
    )

    if world is None:
        world = bpy.data.worlds.new(
            "BPT_PreviewWorld"
        )

        scene.world = (
            world
        )

    world.color = (
        0.04,
        0.04,
        0.04,
    )


# ---------------------------------------------------------
# Still rendering
# ---------------------------------------------------------

def render_still(
    *,
    orbit: bpy.types.Object,
    angle_radians: float,
    output_path: Path,
) -> None:
    scene = (
        bpy.context.scene
    )

    orbit.rotation_euler.z = (
        angle_radians
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
    columns: int = 4,
) -> None:
    if not image_paths:
        raise ValueError(
            "No images for contact sheet."
        )

    images: list[
        bpy.types.Image
    ] = []

    try:
        for path in image_paths:
            image = bpy.data.images.load(
                str(
                    path.resolve()
                ),
                check_existing=False,
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

        if (
            tile_width <= 0
            or tile_height <= 0
        ):
            raise RuntimeError(
                "Invalid contact sheet tile size."
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

        tile_float_count = (
            tile_width
            * tile_height
            * 4
        )

        row_float_count = (
            tile_width
            * 4
        )

        for image_index, image in enumerate(
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
                        "All contact sheet images "
                        "must use the same size."
                    )
                )

            pixels = (
                array(
                    "f",
                    [0.0],
                )
                * tile_float_count
            )

            image.pixels.foreach_get(
                pixels
            )

            column = (
                image_index
                % columns
            )

            top_row = (
                image_index
                // columns
            )

            destination_row = (
                rows
                - 1
                - top_row
            )

            for local_y in range(
                tile_height
            ):
                source_start = (
                    local_y
                    * row_float_count
                )

                source_end = (
                    source_start
                    + row_float_count
                )

                sheet_y = (
                    destination_row
                    * tile_height
                    + local_y
                )

                destination_start = (
                    (
                        sheet_y
                        * sheet_width
                        + column
                        * tile_width
                    )
                    * 4
                )

                destination_end = (
                    destination_start
                    + row_float_count
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

    paths: list[Path] = []

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

        path = (
            stills_dir
            / f"view_{degrees:03d}.png"
        )

        render_still(
            orbit=orbit,
            angle_radians=angle,
            output_path=path,
        )

        paths.append(
            path
        )

    contact_path = (
        output_dir
        / "contact_sheet.png"
    )

    build_contact_sheet(
        paths,
        contact_path,
        columns=4,
    )

    return contact_path


# ---------------------------------------------------------
# Video
# ---------------------------------------------------------

def configure_video_output(
    *,
    output_path: Path,
    frames: int,
    fps: int,
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

    scene.render.fps = (
        fps
    )

    scene.render.image_settings.file_format = (
        "FFMPEG"
    )

    scene.render.filepath = str(
        output_path.resolve()
    )

    scene.render.use_file_extension = (
        True
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


def configure_orbit_driver(
    orbit: bpy.types.Object,
    *,
    frames: int,
) -> None:
    try:
        orbit.driver_remove(
            "rotation_euler",
            2,
        )
    except TypeError:
        pass

    curve = orbit.driver_add(
        "rotation_euler",
        2,
    )

    driver = (
        curve.driver
    )

    driver.type = (
        "SCRIPTED"
    )

    full_rotation = (
        2.0
        * math.pi
    )

    driver.expression = (
        f"{full_rotation}"
        f" * (frame - 1)"
        f" / {frames}"
    )


def render_video(
    *,
    orbit: bpy.types.Object,
    output_dir: Path,
    frames: int,
    fps: int,
) -> Path:
    video_path = (
        output_dir
        / "turntable.mp4"
    )

    configure_orbit_driver(
        orbit,
        frames=frames,
    )

    configure_video_output(
        output_path=video_path,
        frames=frames,
        fps=fps,
    )

    bpy.ops.render.render(
        animation=True
    )

    if not video_path.exists():
        candidates = sorted(
            output_dir.glob(
                "turntable*.mp4"
            )
        )

        if candidates:
            candidate = (
                candidates[0]
            )

            if candidate != video_path:
                candidate.replace(
                    video_path
                )

    if not video_path.exists():
        raise RuntimeError(
            (
                "Blender video rendering "
                "did not produce turntable.mp4"
            )
        )

    return video_path


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

    if (
        args.contact_views < 4
        or args.contact_views > 16
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

    setup_workbench(
        size=args.size
    )

    contact_path = (
        render_contact_sheet(
            orbit=orbit,
            output_dir=output_dir,
            views=args.contact_views,
        )
    )

    video_path = render_video(
        orbit=orbit,
        output_dir=output_dir,
        frames=args.frames,
        fps=args.fps,
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

    print(
        "Visual preview generated"
    )

    print(
        f"Contact sheet: {contact_path}"
    )

    print(
        f"Turntable: {video_path}"
    )


if __name__ == "__main__":
    main()