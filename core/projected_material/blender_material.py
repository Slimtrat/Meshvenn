from __future__ import annotations
import bpy
from .constants import COLOR_ATTRIBUTE_NAME, MATERIAL_NAME

def _ensure_color_attribute(mesh: bpy.types.Mesh, *, attribute_name: str):
    existing = mesh.color_attributes.get(attribute_name)
    if existing is not None:
        if existing.domain != 'CORNER' or existing.data_type != 'FLOAT_COLOR':
            mesh.color_attributes.remove(existing)
            existing = None
    if existing is None:
        existing = mesh.color_attributes.new(name=attribute_name, type='FLOAT_COLOR', domain='CORNER')
    return existing

def ensure_projected_material(*, attribute_name: str=COLOR_ATTRIBUTE_NAME, material_name: str=MATERIAL_NAME) -> bpy.types.Material:
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(name=material_name)
    material.use_nodes = True
    node_tree = material.node_tree
    if node_tree is None:
        raise RuntimeError('Could not create material node tree.')
    nodes = node_tree.nodes
    links = node_tree.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    output.name = 'BPT Material Output'
    output.label = 'BPT Material Output'
    output.location = (420.0, 0.0)
    principled = nodes.new('ShaderNodeBsdfPrincipled')
    principled.name = 'BPT Principled'
    principled.label = 'Projected Material'
    principled.location = (120.0, 0.0)
    if 'Metallic' in principled.inputs:
        principled.inputs['Metallic'].default_value = 0.0
    if 'Roughness' in principled.inputs:
        principled.inputs['Roughness'].default_value = 0.65
    try:
        color_node = nodes.new('ShaderNodeVertexColor')
        color_node.layer_name = attribute_name
    except RuntimeError:
        color_node = nodes.new('ShaderNodeAttribute')
        color_node.attribute_name = attribute_name
    color_node.name = 'BPT Projected Color'
    color_node.label = attribute_name
    color_node.location = (-220.0, 20.0)
    color_output = color_node.outputs.get('Color')
    base_color_input = principled.inputs.get('Base Color')
    if color_output is None or base_color_input is None:
        raise RuntimeError('Could not connect projected color to Principled BSDF.')
    links.new(color_output, base_color_input)
    links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    return material
