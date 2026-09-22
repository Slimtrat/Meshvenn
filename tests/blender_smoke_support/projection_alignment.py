"""Packaged Blender smoke for registered per-view silhouette alignment."""

from __future__ import annotations

import importlib

import bpy

from .support import _require, _section


def _validate_projection_alignment(package_name: str, settings) -> None:
    _section("projection alignment")
    _require(len(settings.projections) >= 2, "Alignment smoke needs two default views")
    first, second = settings.projections[:2]
    original = tuple(
        (view.image, view.flip_x, view.alignment_offset_u,
         view.alignment_offset_v, view.alignment_scale)
        for view in (first, second)
    )
    image = bpy.data.images.new("MeshvennAlignmentSmoke", width=5, height=5, alpha=True)
    try:
        pixels = [0.0] * (5 * 5 * 4)
        center = (2 * 5 + 2) * 4
        pixels[center:center + 4] = (1.0, 0.0, 0.0, 1.0)
        image.pixels.foreach_set(pixels)
        image.update()
        first.image = image
        second.image = image
        first.flip_x = False
        first.alignment_offset_u = 0.25
        first.alignment_offset_v = 0.0
        first.alignment_scale = 1.0
        second.alignment_offset_u = 0.0
        second.alignment_offset_v = 0.0
        second.alignment_scale = 1.0

        pipeline = importlib.import_module(f"{package_name}.core.pipeline_contracts")
        implementation = importlib.import_module(
            f"{package_name}.implementations.projection_images"
        ).ProjectionImagesImplementation()
        result = implementation.execute(pipeline.PipelineContext(scene=bpy.context.scene))
        _require(result.success, f"Aligned projection input failed: {result.message}")
        aligned, neutral = result.payload.views[:2]
        _require(aligned.mask.get(3, 2) and not aligned.mask.get(2, 2),
                 "Silhouette did not shift by one source pixel")
        _require(neutral.mask.get(2, 2) and not neutral.mask.get(3, 2),
                 "Neutral alignment changed the source mask")
        legacy_view = type(neutral)(
            name=neutral.name, image_name=neutral.image_name,
            width=neutral.width, height=neutral.height,
            azimuth_degrees=neutral.azimuth_degrees,
            elevation_degrees=neutral.elevation_degrees,
            flip_x=neutral.flip_x, weight=neutral.weight,
            mask=neutral.mask, native_projection=neutral.native_projection,
            material_view=neutral.material_view,
        )
        _require(legacy_view.alignment.is_identity,
                 "Legacy prepared-view constructors must default to neutral alignment")
        _require(aligned.native_projection.mask is aligned.mask,
                 "Native geometry did not receive the aligned mask")
        _require(aligned.material_view.mask is aligned.mask,
                 "Material did not receive the aligned mask")
        _require(result.metadata["views"][0]["alignment"]["offset_u"] == 0.25,
                 "INPUT metadata omitted the per-view alignment")

        sampling = importlib.import_module(
            f"{package_name}.core.projected_material.sampling"
        )
        candidate = sampling._sample_source_view(
            (1.0, 0.0, 2.0), (0.0, -1.0, 0.0), aligned.material_view,
            width=4, depth=4, height=4, voxel_size=1.0, center_xy=True,
        )
        _require(candidate is not None and candidate.red > 0.99 and candidate.alpha > 0.99,
                 "Material color did not follow the aligned silhouette")
        first.flip_x = True
        flipped = implementation.execute(pipeline.PipelineContext(scene=bpy.context.scene))
        _require(flipped.success, "Flipped aligned input failed")
        flipped_view = flipped.payload.views[0]
        _require(flipped_view.native_projection.flip_x, "Native view lost Flip X")
        flipped_candidate = sampling._sample_source_view(
            (-1.0, 0.0, 2.0), (0.0, -1.0, 0.0), flipped_view.material_view,
            width=4, depth=4, height=4, voxel_size=1.0, center_xy=True,
        )
        _require(flipped_candidate is not None and flipped_candidate.red > 0.99,
                 "Flip X and alignment disagree on material coordinates")
        print("Per-view silhouette and material alignment: OK")
    finally:
        for view, (source_image, flip_x, offset_u, offset_v, scale) in zip((first, second), original):
            view.image = source_image
            view.flip_x = flip_x
            view.alignment_offset_u = offset_u
            view.alignment_offset_v = offset_v
            view.alignment_scale = scale
        bpy.data.images.remove(image, do_unlink=True)
