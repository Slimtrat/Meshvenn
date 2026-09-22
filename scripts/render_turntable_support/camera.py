from __future__ import annotations

import argparse
import math
import shutil
import sys
from array import array
from pathlib import Path
import bpy
from mathutils import Vector

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
