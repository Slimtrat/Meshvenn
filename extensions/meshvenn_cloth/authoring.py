"""Bake a standard portable PBR cloth material without changing the source rig."""

from dataclasses import asdict
import json, math
from array import array
import bpy
from .config import ClothConfig
from .nodes import procedural_detail, portable_images


def _run_bake(kind):
    return bpy.ops.object.bake(type=kind, use_selected_to_active=False)


def apply_cloth(obj, config=None):
    config = config or ClothConfig()
    if (
        obj is None
        or obj.type != "MESH"
        or len(obj.data.materials) != 1
        or obj.data.uv_layers.active is None
    ):
        raise ValueError("Select one UV-mapped mesh with a single material")
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        raise ValueError("Use Object Mode")
    for modifier in obj.modifiers:
        if modifier.type == "ARMATURE" and modifier.object:
            for bone in modifier.object.pose.bones:
                values = [x for row in bone.matrix_basis for x in row]
                if (
                    any(not math.isfinite(x) for x in values)
                    or max(
                        abs(x - (1.0 if i == j else 0.0))
                        for i, row in enumerate(bone.matrix_basis)
                        for j, x in enumerate(row)
                    )
                    > 2e-5
                ):
                    raise ValueError("Bake cloth in the native rest pose")
    if any(p.material_index != 0 for p in obj.data.polygons):
        raise ValueError("Unexpected material assignment")
    original = obj.data.materials[0]
    if original is None or original.node_tree is None:
        raise ValueError("Require a baked node material")
    outputs = [
        n
        for n in original.node_tree.nodes
        if n.type == "OUTPUT_MATERIAL" and n.is_active_output
    ]
    if len(outputs) != 1 or len(outputs[0].inputs["Surface"].links) != 1:
        raise ValueError("Require one active surface shader")
    source_shader = outputs[0].inputs["Surface"].links[0].from_node
    if source_shader.type != "BSDF_PRINCIPLED":
        raise ValueError("Require a Principled material")
    if (
        source_shader.inputs["Normal"].is_linked
        and "meshvenn_cloth_config" not in original
    ):
        raise ValueError("Keep existing authored normal maps in a separate material")
    color = source_shader.inputs["Base Color"]
    if not color.is_linked or color.links[0].from_node.type != "TEX_IMAGE":
        raise ValueError("Require a baked base-color image")
    base = color.links[0].from_node.image
    if base is None or len(base.pixels) == 0:
        raise ValueError("Missing base-color pixels")
    material = original.copy()
    material.name = original.name + " Cloth"
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    shader = nodes.get(source_shader.name)
    output = nodes.get(outputs[0].name)
    normal_socket, rough_socket = procedural_detail(
        material, shader.inputs["Base Color"].links[0].from_socket, config
    )
    links.new(normal_socket, shader.inputs["Normal"])
    scene = bpy.context.scene
    layer = bpy.context.view_layer
    old_engine = scene.render.engine
    old_samples = scene.cycles.samples
    old_bake_margin = scene.render.bake.margin
    old_bake_clear = scene.render.bake.use_clear
    old_normal_space = scene.render.bake.normal_space
    old_selected = list(bpy.context.selected_objects)
    old_active = layer.objects.active
    images = []
    success = False
    try:
        obj.data.materials[0] = material
        for item in old_selected:
            item.select_set(False)
        obj.select_set(True)
        layer.objects.active = obj
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 4
        scene.render.bake.margin = max(4, config.texture_size // 128)
        scene.render.bake.use_clear = True
        scene.render.bake.normal_space = "TANGENT"
        target = nodes.new("ShaderNodeTexImage")
        target.name = "Cloth bake target"

        def bake(name, kind):
            image = bpy.data.images.new(
                obj.name + " " + name,
                width=config.texture_size,
                height=config.texture_size,
                alpha=False,
            )
            images.append(image)
            image.colorspace_settings.name = "Non-Color"
            target.image = image
            for n in nodes:
                n.select = False
            target.select = True
            nodes.active = target
            result = _run_bake(kind)
            if "FINISHED" not in result:
                raise RuntimeError("Cloth " + name + " bake failed")
            image.pack()
            return image

        normal = bake("Cloth Normal", "NORMAL")
        emission = nodes.new("ShaderNodeEmission")
        links.new(rough_socket, emission.inputs["Color"])
        links.new(emission.outputs[0], output.inputs["Surface"])
        roughness = bake("Cloth Roughness", "EMIT")
        # glTF stores metallic/roughness as B/G. Author that portable packing
        # explicitly so the export does not repack a grayscale source image.
        packed = array("f", [0.0]) * len(roughness.pixels)
        roughness.pixels.foreach_get(packed)
        for i in range(0, len(packed), 4):
            packed[i] = 1.0
            packed[i + 2] = 0.0
            packed[i + 3] = 1.0
        roughness.pixels.foreach_set(packed)
        roughness.pack()
        links.new(shader.outputs["BSDF"], output.inputs["Surface"])
        nodes.remove(target)
        portable_images(
            material, shader, obj.data.uv_layers.active.name, normal, roughness
        )
        shader.inputs["Metallic"].default_value = 0.0
        # Unused while linked; Blender's glTF importer restores this default.
        shader.inputs["Roughness"].default_value = 0.5
        reachable = set()

        def visit(node):
            if node in reachable:
                return
            reachable.add(node)
            for socket in node.inputs:
                for link in socket.links:
                    visit(link.from_node)

        visit(output)
        for node in list(nodes):
            if node not in reachable:
                nodes.remove(node)
        material["meshvenn_cloth_config"] = json.dumps(asdict(config), sort_keys=True)
        material["meshvenn_cloth_detail_authority"] = (
            "Authored procedural weave and roughness; not image observations"
        )
        success = True
        return dict(
            material=material,
            base_color=base,
            normal=normal,
            roughness=roughness,
            config=asdict(config),
        )
    finally:
        scene.render.engine = old_engine
        scene.cycles.samples = old_samples
        scene.render.bake.margin = old_bake_margin
        scene.render.bake.use_clear = old_bake_clear
        scene.render.bake.normal_space = old_normal_space
        for item in list(bpy.context.selected_objects):
            item.select_set(False)
        for item in old_selected:
            if item.name in layer.objects:
                item.select_set(True)
        layer.objects.active = old_active
        if not success:
            obj.data.materials[0] = original
            bpy.data.materials.remove(material)
            for image in images:
                if image.users == 0:
                    bpy.data.images.remove(image)
