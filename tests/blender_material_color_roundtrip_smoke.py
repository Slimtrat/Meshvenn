"""Non-primary linear RGB through emission, PNG, UV image, GLB and reimport."""
from __future__ import annotations
import importlib
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))
OUT = ROOT / "tmp/material-color-probe"
OUT.mkdir(parents=True, exist_ok=True)
COLOR = (.25, .50, .75)


def module(name):
    return importlib.import_module(f"{ROOT.name}.{name}")


def center_rgb(image):
    buffer = module("core.projected_material").ImageBuffer.from_blender_image(image)
    return buffer.rgba(buffer.width // 2, buffer.height // 2)[:3]


def assert_color(value, label, tolerance=.012):
    error = max(abs(actual - expected) for actual, expected in zip(value, COLOR))
    print(f"{label}: {value}, linear RGB error {error:.8f}")
    if error > tolerance:
        raise AssertionError(f"{label} changed source linear RGB: {value} != {COLOR}")


def render_probe(obj, path):
    from scripts.render_turntable import setup_render, create_camera
    from scripts.render_material_projections import _emit_base_color
    _emit_base_color([obj])
    camera = create_camera(target=Vector(), model_size=Vector((2, 2, 0)))
    camera.location = (0, 0, 3)
    camera.rotation_euler = (0, 0, 0)
    camera.data.ortho_scale = 2
    setup_render(size=20, samples=1)
    scene = bpy.context.scene
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "16"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(path), check_existing=False)
    color = center_rgb(image)
    bpy.data.images.remove(image)
    bpy.data.objects.remove(camera, do_unlink=True)
    return color


def main():
    from scripts.render_turntable import clear_scene
    clear_scene()
    mesh = bpy.data.meshes.new("LinearColorProof")
    mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    obj = bpy.data.objects.new("LinearColorProof", mesh)
    bpy.context.scene.collection.objects.link(obj)
    material = bpy.data.materials.new("KnownNonPrimaryBaseColor")
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = (*COLOR, 1)
    mesh.materials.append(material)
    source_rgb = render_probe(obj, OUT / "source.png")
    assert_color(source_rgb, "BaseColor emission -> PNG16 -> ImageBuffer")
    bake = module("core.uv_bake")
    corners = [bake.UVBakeVertex(tuple(vertex.co), (0, 0, 1), uv) for vertex, uv in
               zip(mesh.vertices, ((0, 0), (1, 0), (1, 1), (0, 1)))]
    result = bake.bake_uv_texture([bake.UVBakeTriangle(*[corners[i] for i in indices]) for indices in
                                 ((0, 1, 2), (0, 2, 3))], lambda position, normal: (*source_rgb, 1),
                                config=bake.UVBakeConfig(width=16, height=16, padding_pixels=0, samples_per_axis=2))
    assets = module("implementations.uv_bake.assets")
    image = assets._create_baked_image(obj, result)
    print("Generated UV image color space:", image.colorspace_settings.name)
    # Byte-image RNA returns encoded UNORM8, not scene-linear shader color.
    from math import pow
    encoded = tuple(1.055 * pow(value, 1/2.4) - .055 for value in COLOR)
    assert max(abs(actual - expected) for actual, expected in zip(center_rgb(image), encoded)) < .004
    uv = mesh.uv_layers.new(name="ProofUV")
    for loop in mesh.loops:
        uv.data[loop.index].uv = corners[loop.vertex_index].uv
    baked_material = assets._create_baked_material(obj, image=image, uv_layer_name=uv.name)
    mesh.materials.clear()
    mesh.materials.append(baked_material)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = OUT / "color.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True)
    assert_color(render_probe(obj, OUT / "baked.png"), "UV RGBA8 -> material emission")
    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = next(item for item in bpy.context.scene.objects if item.type == "MESH")
    assert_color(render_probe(imported, OUT / "reimport.png"), "GLB texture -> reimport emission")
    print("Non-primary linear RGB material roundtrip PASS")


if __name__ == "__main__":
    main()
