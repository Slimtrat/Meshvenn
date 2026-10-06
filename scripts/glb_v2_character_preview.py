"""Neutral, three-quarter preview of the actually reconstructed rest GLB."""
import math
from pathlib import Path

import bpy

from scripts.render_turntable import (
    clear_scene, import_glb, center_objects, ensure_preview_material,
    create_camera, setup_lighting, setup_render, look_at,
)


def render_character_preview(input_path: Path, output_path: Path) -> None:
    clear_scene()
    objects = import_glb(input_path)
    target, size = center_objects(objects)
    ensure_preview_material(objects)
    camera = create_camera(target=target, model_size=size)
    distance = max(size)*3
    camera.location = (math.sin(math.pi/6)*distance, -math.cos(math.pi/6)*distance,
                       size.z*.2)
    look_at(camera, target)
    setup_lighting(size)
    setup_render(size=768, samples=32)
    bpy.context.scene.render.filepath = str(output_path.resolve())
    bpy.ops.render.render(write_still=True)
    if not output_path.is_file():
        raise AssertionError("Character preview was not rendered")
