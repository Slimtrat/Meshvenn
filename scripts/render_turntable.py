from __future__ import annotations

import argparse
import math
import sys
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
            "Render a headless turntable preview "
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
        default=36,
    )

    parser.add_argument(
        "--size",
        type=int,
        default=512,
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=32,
    )

    return parser.parse_args(
        argv
    )


# ---------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------

def clear_scene() -> None:
    for obj in tuple(
        bpy.data.objects
    ):
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )


def import_glb(
    path: Path,
) -> list[bpy.types.Object]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing GLB: {path}"
        )

    before = set(
        bpy.data.objects
    )

    bpy.ops.import_scene.gltf(
        filepath=str(
            path.resolve()
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


def combined_bounds(
    objects: list[bpy.types.Object],
) -> tuple[Vector, Vector]:
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
        matrix = obj.matrix_world

        for corner in obj.bound_box:
            point = (
                matrix
                @ Vector(corner)
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
) -> tuple[Vector, float]:
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

    size = (
        max_corner
        - min_corner
    )

    radius = max(
        size.x,
        size.y,
        size.z,
    ) * 0.5

    if radius <= 0.0:
        radius = 1.0

    for obj in objects:
        obj.location -= (
            center
        )

    return (
        Vector(
            (
                0.0,
                0.0,
                0.0,
            )
        ),
        radius,
    )


# ---------------------------------------------------------
# Camera
# ---------------------------------------------------------

def create_camera(
    target: Vector,
    radius: float,
) -> bpy.types.Object:
    camera_data = (
        bpy.data.cameras.new(
            "TurntableCamera"
        )
    )

    camera = (
        bpy.data.objects.new(
            "TurntableCamera",
            camera_data,
        )
    )

    bpy.context.scene.collection.objects.link(
        camera
    )

    bpy.context.scene.camera = (
        camera
    )

    camera_data.type = (
        "ORTHO"
    )

    camera_data.ortho_scale = (
        radius
        * 2.6
    )

    camera.data.lens = (
        50.0
    )

    look_at(
        camera,
        target,
    )

    return camera


def look_at(
    obj: bpy.types.Object,
    target: Vector,
) -> None:
    direction = (
        target
        - obj.location
    )

    obj.rotation_euler = (
        direction
        .to_track_quat(
            "-Z",
            "Y",
        )
        .to_euler()
    )


# ---------------------------------------------------------
# Lighting
# ---------------------------------------------------------

def add_area_light(
    name: str,
    location: tuple[
        float,
        float,
        float,
    ],
    energy: float,
    size: float,
) -> bpy.types.Object:
    data = bpy.data.lights.new(
        name=name,
        type="AREA",
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

    light = bpy.data.objects.new(
        name,
        data,
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
    radius: float,
) -> None:
    distance = (
        radius
        * 3.5
    )

    size = (
        radius
        * 2.0
    )

    add_area_light(
        "Key",
        (
            distance,
            -distance,
            distance * 1.2,
        ),
        energy=1000.0,
        size=size,
    )

    add_area_light(
        "Fill",
        (
            -distance,
            -distance * 0.5,
            distance * 0.7,
        ),
        energy=500.0,
        size=size,
    )

    add_area_light(
        "Rim",
        (
            0.0,
            distance,
            distance,
        ),
        energy=700.0,
        size=size,
    )


# ---------------------------------------------------------
# Ground
# ---------------------------------------------------------

def add_ground(
    radius: float,
) -> None:
    bpy.ops.mesh.primitive_plane_add(
        size=radius * 8.0,
        location=(
            0.0,
            0.0,
            -radius,
        ),
    )

    plane = (
        bpy.context.active_object
    )

    plane.name = (
        "TurntableGround"
    )


# ---------------------------------------------------------
# Render setup
# ---------------------------------------------------------

def setup_render(
    output_dir: Path,
    *,
    size: int,
    samples: int,
) -> None:
    scene = bpy.context.scene

    scene.render.engine = (
        "BLENDER_EEVEE_NEXT"
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

    scene.render.image_settings.file_format = (
        "PNG"
    )

    scene.render.film_transparent = (
        False
    )

    scene.render.filepath = str(
        (
            output_dir
            / "frames"
            / "000.png"
        ).resolve()
    )

    scene.render.image_settings.color_mode = (
        "RGBA"
    )

    scene.render.image_settings.color_depth = (
        "8"
    )

    scene.render.engine = (
        "BLENDER_EEVEE_NEXT"
    )

    world = scene.world

    if world is None:
        world = bpy.data.worlds.new(
            "TurntableWorld"
        )

        scene.world = (
            world
        )

    world.color = (
        0.035,
        0.035,
        0.035,
    )


# ---------------------------------------------------------
# Materials
# ---------------------------------------------------------

def ensure_preview_material(
    objects: list[bpy.types.Object],
) -> None:
    material = (
        bpy.data.materials.new(
            "TurntablePreviewMaterial"
        )
    )

    material.diffuse_color = (
        0.45,
        0.47,
        0.5,
        1.0,
    )

    material.roughness = (
        0.65
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
# Turntable
# ---------------------------------------------------------

def render_turntable(
    camera: bpy.types.Object,
    *,
    target: Vector,
    radius: float,
    frames: int,
    output_dir: Path,
) -> None:
    frames_dir = (
        output_dir
        / "frames"
    )

    frames_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    distance = (
        radius
        * 3.2
    )

    camera_height = (
        radius
        * 0.25
    )

    for frame in range(
        frames
    ):
        angle = (
            2.0
            * math.pi
            * frame
            / frames
        )

        camera.location = (
            distance
            * math.sin(
                angle
            ),
            -distance
            * math.cos(
                angle
            ),
            camera_height,
        )

        look_at(
            camera,
            target,
        )

        bpy.context.scene.render.filepath = str(
            (
                frames_dir
                / f"{frame:03d}.png"
            ).resolve()
        )

        bpy.ops.render.render(
            write_still=True
        )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.frames < 4:
        raise ValueError(
            "frames must be >= 4"
        )

    if args.size < 128:
        raise ValueError(
            "size must be >= 128"
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
        args.input.resolve()
    )

    (
        target,
        radius,
    ) = center_objects(
        objects
    )

    ensure_preview_material(
        objects
    )

    camera = create_camera(
        target,
        radius,
    )

    setup_lighting(
        radius
    )

    add_ground(
        radius
    )

    setup_render(
        output_dir,
        size=args.size,
        samples=args.samples,
    )

    render_turntable(
        camera,
        target=target,
        radius=radius,
        frames=args.frames,
        output_dir=output_dir,
    )

    print(
        (
            "Turntable rendered: "
            f"{output_dir}"
        )
    )


if __name__ == "__main__":
    main()