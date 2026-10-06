"""Small real Blender qualification of the portable UV color transport."""
from __future__ import annotations
from pathlib import Path
import bpy
from mathutils import Vector


def certify_material_color_transport(output: Path, module):
    from scripts.render_turntable import clear_scene, setup_render, create_camera
    from scripts.render_material_projections import _emit_base_color
    output.mkdir(parents=True, exist_ok=True)
    expected, tolerance = (.25, .50, .75), .004
    projected = module("core.projected_material")

    def rgb(image):
        buffer = projected.ImageBuffer.from_blender_image(image)
        return buffer.rgba(buffer.width // 2, buffer.height // 2)[:3]

    def render(obj, name):
        _emit_base_color([obj])
        camera = create_camera(target=Vector(), model_size=Vector((2, 2, 0)))
        camera.location, camera.rotation_euler = (0, 0, 3), (0, 0, 0)
        camera.data.ortho_scale = 2
        setup_render(size=20, samples=1)
        scene = bpy.context.scene
        scene.render.film_transparent = True
        scene.render.image_settings.color_mode, scene.render.image_settings.color_depth = "RGBA", "16"
        scene.view_settings.view_transform, scene.view_settings.look = "Standard", "None"
        scene.view_settings.exposure, scene.view_settings.gamma = 0, 1
        path = output / f"{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(str(path), check_existing=False)
        result = rgb(image)
        bpy.data.images.remove(image)
        bpy.data.objects.remove(camera, do_unlink=True)
        return result

    clear_scene()
    try:
        mesh = bpy.data.meshes.new("ColorTransportProof")
        mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
        obj = bpy.data.objects.new("ColorTransportProof", mesh)
        bpy.context.scene.collection.objects.link(obj)
        source = bpy.data.materials.new("KnownNonPrimaryBaseColor")
        source.use_nodes = True
        shader = next(node for node in source.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        shader.inputs["Base Color"].default_value = (*expected, 1)
        mesh.materials.append(source)
        source_rgb = render(obj, "source")
        bake = module("core.uv_bake")
        corners = [bake.UVBakeVertex(tuple(vertex.co), (0, 0, 1), uv) for vertex, uv in
                   zip(mesh.vertices, ((0, 0), (1, 0), (1, 1), (0, 1)))]
        result = bake.bake_uv_texture([bake.UVBakeTriangle(*[corners[index] for index in indices])
                                      for indices in ((0, 1, 2), (0, 2, 3))],
                                     lambda position, normal: (*source_rgb, 1),
                                     config=bake.UVBakeConfig(width=16, height=16, padding_pixels=0,
                                                              samples_per_axis=2))
        assets = module("implementations.uv_bake.assets")
        image = assets._create_baked_image(obj, result)
        uv = mesh.uv_layers.new(name="ProofUV")
        for loop in mesh.loops:
            uv.data[loop.index].uv = corners[loop.vertex_index].uv
        material = assets._create_baked_material(obj, image=image, uv_layer_name=uv.name)
        mesh.materials.clear()
        mesh.materials.append(material)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        path = output / "color.glb"
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True)
        baked_rgb = render(obj, "baked")
        clear_scene()
        bpy.ops.import_scene.gltf(filepath=str(path))
        imported = next(item for item in bpy.context.scene.objects if item.type == "MESH")
        imported_rgb = render(imported, "reimport")
        maximum = max(abs(actual - reference) for values in (source_rgb, baked_rgb, imported_rgb)
                      for actual, reference in zip(values, expected))
        report = {"passed": maximum <= tolerance, "source_linear_rgb": list(expected),
                  "source_projection_linear_rgb": list(source_rgb), "baked_shader_linear_rgb": list(baked_rgb),
                  "reimported_shader_linear_rgb": list(imported_rgb), "max_linear_error": maximum,
                  "tolerance": tolerance, "atlas_storage": "srgb-byte-from-scene-linear"}
        if not report["passed"]:
            raise AssertionError(f"Portable UV color transport failed: {report}")
        return report
    finally:
        clear_scene()
