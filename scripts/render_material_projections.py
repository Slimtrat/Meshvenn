"""Render calibrated base-color inputs separately from geometry silhouettes.

Uses an already isolated, unrigged reference and the same native-normalized
camera primitives as geometry, but retains transparent alpha and emits the
actual imported Principled Base Color graph. No lighting or baked shadows.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import bpy

from scripts.render_projection_sheet_support.camera import configure_projection_render
from scripts.render_projection_sheet_support.layout import build_cells
from scripts.render_projection_sheet_support.render import render_view
from scripts.render_turntable import clear_scene, import_glb, center_objects, create_camera


def _emit_base_color(objects):
    seen, captures = set(), []
    for obj in objects:
        if obj.type != "MESH" or any(mod.type == "ARMATURE" for mod in obj.modifiers):
            raise ValueError("Appearance rendering requires an isolated unrigged mesh.")
        for material in obj.data.materials:
            if material is None or material in seen:
                continue
            seen.add(material)
            if not material.use_nodes:
                raise ValueError("Source appearance must expose its real Base Color graph.")
            nodes, links = material.node_tree.nodes, material.node_tree.links
            outputs = [node for node in nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output]
            if len(outputs) != 1:
                raise ValueError("Source material has no unambiguous active output.")
            surface = outputs[0].inputs["Surface"]
            if len(surface.links) != 1 or surface.links[0].from_node.type != "BSDF_PRINCIPLED":
                raise ValueError("Base-color capture requires an active Principled source material.")
            shader = surface.links[0].from_node
            alpha = shader.inputs["Alpha"]
            if alpha.is_linked or abs(alpha.default_value - 1) > 1e-6:
                raise ValueError("Base-color capture currently supports opaque source alpha only.")
            captures.append((nodes, links, shader.inputs["Base Color"], surface))
    if not seen:
        raise ValueError("Source has no material to capture.")
    # Validate every source first: a later unsupported material cannot leave
    # earlier material graphs partially replaced on a rejected capture.
    for nodes, links, color, surface in captures:
        emission = nodes.new("ShaderNodeEmission")
        if color.is_linked:
            links.new(color.links[0].from_socket, emission.inputs["Color"])
        else:
            emission.inputs["Color"].default_value = color.default_value
        emission.inputs["Strength"].default_value = 1
        links.new(emission.outputs[0], surface)


def render_material_projections(input_glb: Path, output: Path, *, sheet_width=3000,
                                sheet_height=1800, framing=1.15):
    """Dedicated batch producer; imported source objects are always discarded.

    Color management is explicitly Standard/sRGB, exposure 0, gamma 1. PNG
    reload converts those display pixels to scene-linear RGB for UV baking.
    One emission sample is noiseless on interiors; alpha AA remains measured.
    """
    output.mkdir(parents=True, exist_ok=True)
    payload = input_glb.read_bytes()
    if payload[:4] != b"glTF" or payload[16:20] != b"JSON":
        raise ValueError("Appearance source must be a GLB with a JSON document.")
    length = struct.unpack_from("<I", payload, 12)[0]
    document = json.loads(payload[20:20 + length])
    if any(material.get("alphaMode", "OPAQUE") != "OPAQUE" for material in document.get("materials", [])):
        raise ValueError("Base-color capture currently supports GLB OPAQUE materials only.")
    clear_scene()
    try:
        objects = import_glb(input_glb)
        if any(obj.type == "ARMATURE" for obj in bpy.context.scene.objects):
            raise ValueError("Appearance source must not expose a source armature.")
        target, size = center_objects(objects)
        _emit_base_color(objects)
        camera = create_camera(target=target, model_size=size)
        configure_projection_render(samples=1)
        scene = bpy.context.scene
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
        scene.render.image_settings.color_depth = "16"
        side = max(size) * framing
        views = []
        for name, azimuth, elevation, bbox in build_cells(sheet_width, sheet_height, inset=0):
            path = render_view(camera=camera, target=target, model_size=size,
                               name=name, azimuth=azimuth, elevation=elevation, bbox=bbox,
                               ortho_scale=side, output_dir=output, native_side=side)
            views.append(SimpleNamespace(name=name, path=path, azimuth_degrees=azimuth,
                                         elevation_degrees=elevation))
        return views, {"render_mode": "base-color-emission", "render_samples": 1,
                       "lighting_baked": False, "projection_convention": "native-normalized",
                       "framing": framing, "color_space": "scene-linear RGB via Standard/sRGB 16-bit PNG",
                       "views": [{"name": view.name, "sha256": hashlib.sha256(view.path.read_bytes()).hexdigest(),
                                  "azimuth_degrees": view.azimuth_degrees,
                                  "elevation_degrees": view.elevation_degrees} for view in views]}
    finally:
        clear_scene()
