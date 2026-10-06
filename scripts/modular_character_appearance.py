"""Bind image-only appearance inputs to the fixture's unchanged geometry."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import bpy

from scripts.modular_appearance_evidence import image_signal


def prepare_appearance(geometry, rendered, provenance, module):
    image_api = module("core.projected_material.image_buffer")
    masks = module("core.image_mask")
    input_api = module("core.material_inputs")
    paths = {view.name: view.path for view in rendered}
    views, signals = [], []
    for original in geometry.source.material_views:
        image = bpy.data.images.load(str(paths[original.name].resolve()), check_existing=False)
        image.name = f"Appearance {original.name}"
        image.use_fake_user = True
        image.pack()
        buffer = image_api.ImageBuffer.from_blender_image(image)
        mask = masks.rgba_to_mask(pixels=buffer.pixels, width=buffer.width, height=buffer.height, alpha_threshold=.1)
        views.append(replace(original, image=buffer, mask=original.alignment.align_mask(mask)))
        signal = image_signal(buffer.pixels, mask.values)
        signals.append({"name": original.name, **signal})
        record = next(record for record in provenance["views"] if record["name"] == original.name)
        record.update(width=buffer.width, height=buffer.height, alpha_occupied_pixels=mask.occupied_count,
                      packed_image=image.name)
    appearance = input_api.MaterialProjectionInput(
        views=tuple(views), projection_space=geometry.projection_space,
        source_sha256=provenance["source_sha256"], render_mode=provenance["render_mode"])
    appearance.validate_for(geometry)
    return appearance, signals


def save_appearance_provenance(provenance):
    import json
    text = bpy.data.texts.new("meshvenn-material-input.json")
    text.use_fake_user = True
    text.write(json.dumps(provenance, indent=2, allow_nan=False))
