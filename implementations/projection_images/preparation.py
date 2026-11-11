from __future__ import annotations

import math
from array import array

import bpy

from ...core.image_mask import rgba_to_mask
from ...core.native_bridge import NativeProjection
from ...core.projection_alignment import ProjectionAlignment
from ...core.projected_material import ProjectedMaterialView
from ...core.projected_material.image_buffer import ImageBuffer
from .models import PreparedProjectionView
from .preflight import CertifiedProjectionBinding


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
    source_mask = rgba_to_mask(
        pixels=pixels,
        width=width,
        height=height,
        alpha_threshold=alpha_threshold,
    )
    alignment = ProjectionAlignment(
        offset_u=float(getattr(projection, "alignment_offset_u", 0.0)),
        offset_v=float(getattr(projection, "alignment_offset_v", 0.0)),
        scale=float(getattr(projection, "alignment_scale", 1.0)),
    )
    mask = alignment.align_mask(source_mask)
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
    material_view = ProjectedMaterialView.from_image_buffer(
        name=name,
        image_buffer=ImageBuffer.from_copied_blender_pixels(image, pixels, width=width, height=height),
        azimuth_degrees=azimuth_degrees,
        elevation_degrees=elevation_degrees,
        flip_x=flip_x,
        weight=weight,
        alignment=alignment,
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
        alignment=alignment,
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


def prepare_certified_projection(projection, certified: CertifiedProjectionBinding) -> PreparedProjectionView:
    """Use one reproduced mapping, preserved RGBA and mask for both consumers.

    The explicit bound source replaces the scene image for this view; scene
    images/settings are never modified. Double buffers preserve decoded values
    exactly instead of silently rounding the hashed float64 source to float32.
    """
    accepted = certified.accepted
    source = accepted.source.image
    camera = certified.revision.camera
    weight = float(projection.weight)
    if not math.isfinite(weight) or weight < 0:
        raise ValueError("Bound projection weight must be finite and nonnegative.")
    mask = accepted.aligned_mask
    alignment = accepted.alignment
    image_buffer = ImageBuffer(source.width, source.height, array("d", source.rgba),
                               alpha_mode="STRAIGHT", rgb_encoding=certified.binding.rgb_encoding)
    image_buffer.validate_coverage_data()
    native = NativeProjection(mask, camera.azimuth_degrees, camera.elevation_degrees, camera.flip_x)
    material = ProjectedMaterialView.from_image_buffer(
        name=certified.binding.projection_name, image_buffer=image_buffer,
        azimuth_degrees=camera.azimuth_degrees, elevation_degrees=camera.elevation_degrees,
        flip_x=camera.flip_x, weight=weight, mask=mask, alignment=alignment)
    return PreparedProjectionView(
        name=certified.binding.projection_name,
        image_name=f"preflight:{certified.revision.view_id}@{certified.revision.revision}",
        width=source.width, height=source.height, azimuth_degrees=camera.azimuth_degrees,
        elevation_degrees=camera.elevation_degrees, flip_x=camera.flip_x, weight=weight,
        mask=mask, native_projection=native, material_view=material,
        alignment=alignment, preflight=certified)
