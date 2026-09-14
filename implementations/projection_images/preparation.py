from __future__ import annotations

import math
from array import array

import bpy

from ...core.image_mask import rgba_to_mask
from ...core.native_bridge import NativeProjection
from ...core.projected_material import ProjectedMaterialView
from .models import PreparedProjectionView


def image_pixels(image: bpy.types.Image) -> tuple[array, int, int]:
    """Copy one Blender image buffer for mask generation."""

    image.update()
    width, height = int(image.size[0]), int(image.size[1])
    if width <= 0 or height <= 0:
        raise ValueError(f'Image "{image.name}" has invalid dimensions: {width}x{height}.')
    expected_float_count = width * height * 4
    pixels = array("f", [0.0]) * expected_float_count
    image.pixels.foreach_get(pixels)
    if len(pixels) != expected_float_count:
        raise RuntimeError(f'Image "{image.name}" returned an unexpected pixel buffer size.')
    return pixels, width, height


def prepare_projection(projection, *, alpha_threshold: float) -> PreparedProjectionView:
    image = projection.image
    if image is None:
        raise ValueError(f'Projection "{projection.name}" has no image.')

    pixels, width, height = image_pixels(image)
    mask = rgba_to_mask(
        pixels=pixels,
        width=width,
        height=height,
        alpha_threshold=alpha_threshold,
    )
    azimuth_degrees = math.degrees(float(projection.azimuth))
    elevation_degrees = math.degrees(float(projection.elevation))
    flip_x = bool(projection.flip_x)
    weight = max(0.0, float(projection.weight))
    name = str(projection.name).strip() or "Projection"

    native_projection = NativeProjection(
        mask=mask,
        azimuth_degrees=azimuth_degrees,
        elevation_degrees=elevation_degrees,
        flip_x=flip_x,
    )
    material_view = ProjectedMaterialView.from_blender_image(
        name=name,
        image=image,
        azimuth_degrees=azimuth_degrees,
        elevation_degrees=elevation_degrees,
        flip_x=flip_x,
        weight=weight,
        mask=mask,
    )
    return PreparedProjectionView(
        name=name,
        image_name=str(image.name),
        width=width,
        height=height,
        azimuth_degrees=azimuth_degrees,
        elevation_degrees=elevation_degrees,
        flip_x=flip_x,
        weight=weight,
        mask=mask,
        native_projection=native_projection,
        material_view=material_view,
    )


def projection_counts(settings) -> tuple[int, int]:
    enabled = ready = 0
    for projection in settings.projections:
        if projection.enabled:
            enabled += 1
            ready += projection.image is not None
    return enabled, ready
