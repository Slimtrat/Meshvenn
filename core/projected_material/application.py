from __future__ import annotations
import math
from array import array
import bpy
from ..material_blend import MaterialBlendConfig
from ..material_visibility import MeshVisibilityTester, VisibilityConfig
from ..projection_math import normalize3
from .constants import BLEND_MODE, COLOR_ATTRIBUTE_NAME, DEFAULT_FALLBACK_COLOR, MATERIAL_MODE, MATERIAL_NAME, VISIBILITY_MODE
from .models import MaterialProjectionStats, ProjectedMaterialView
from .blending import _blend_projected_color_detailed, _resolve_blend_config
from .blender_material import _ensure_color_attribute, ensure_projected_material

def apply_projected_material(obj: bpy.types.Object, views: list[ProjectedMaterialView], *, volume_width: int, volume_depth: int, volume_height: int, voxel_size: float=1.0, center_xy: bool=True, attribute_name: str=COLOR_ATTRIBUTE_NAME, material_name: str=MATERIAL_NAME, facing_power: float=2.0, fallback_color: tuple[float, float, float, float]=DEFAULT_FALLBACK_COLOR, allow_backface_fallback: bool=True, replace_materials: bool=True, enable_visibility: bool=True, visibility_config: VisibilityConfig | None=None, visibility_tester: MeshVisibilityTester | None=None, blend_config: MaterialBlendConfig | None=None) -> MaterialProjectionStats:
    """
    Project source images onto one generated mesh.

    IMPORTANT:

    Call this while obj.data remains in native reconstruction
    coordinates.

    Do this BEFORE scale_object_to_height() or arbitrary mesh
    transforms.

    ---------------------------------------------------------
    V1.1
    ---------------------------------------------------------

        visibility / occlusion via one mesh-local BVH

    ---------------------------------------------------------
    V1.2
    ---------------------------------------------------------

        smooth grazing cutoff
            +
        relative candidate cutoff
            +
        top-K contributor selection
            +
        weight sharpening

    `blend_config` owns V1.2 selection parameters.

    If omitted, defaults are:

        min_facing             = 0.10
        facing_power           = facing_power argument
        relative_score_cutoff  = 0.20
        max_contributors       = 3
        weight_power           = 1.5
    """
    if obj.type != 'MESH':
        raise TypeError('Projected material target must be a mesh object.')
    if not views:
        raise ValueError('At least one material projection is required.')
    if volume_width <= 0 or volume_depth <= 0 or volume_height <= 0:
        raise ValueError('Volume dimensions must be greater than zero.')
    if not math.isfinite(voxel_size) or voxel_size <= 0.0:
        raise ValueError('voxel_size must be finite and greater than zero.')
    if not enable_visibility and visibility_tester is not None:
        raise ValueError('visibility_tester cannot be provided when enable_visibility is False.')
    if visibility_tester is not None and visibility_config is not None:
        raise ValueError('visibility_config cannot be combined with an explicit visibility_tester.')
    resolved_blend_config = _resolve_blend_config(blend_config, facing_power=facing_power)
    mesh = obj.data
    mesh.update()
    vertex_count = len(mesh.vertices)
    loop_count = len(mesh.loops)
    if vertex_count == 0:
        raise ValueError('Cannot project material onto an empty mesh.')
    if loop_count == 0:
        raise ValueError('Cannot project material onto a mesh without loops.')
    active_visibility_tester: MeshVisibilityTester | None
    if enable_visibility:
        active_visibility_tester = visibility_tester
        if active_visibility_tester is None:
            active_visibility_tester = MeshVisibilityTester.from_blender_object(obj, config=visibility_config)
    else:
        active_visibility_tester = None
    vertex_colors: list[tuple[float, float, float, float]] = [fallback_color] * vertex_count
    projected_vertices = 0
    fallback_vertices = 0
    projected_fallback_vertices = 0
    neutral_fallback_vertices = 0
    accepted_samples = 0
    rejected_samples = 0
    candidate_samples = 0
    source_rejected_samples = 0
    visible_samples = 0
    occluded_samples = 0
    front_facing_samples = 0
    backface_samples = 0
    grazing_rejected_samples = 0
    relative_rejected_samples = 0
    top_k_rejected_samples = 0
    selected_samples = 0
    for vertex in mesh.vertices:
        position = (float(vertex.co.x), float(vertex.co.y), float(vertex.co.z))
        normal = normalize3((float(vertex.normal.x), float(vertex.normal.y), float(vertex.normal.z)))
        result = _blend_projected_color_detailed(position, normal, views, width=volume_width, depth=volume_depth, height=volume_height, voxel_size=voxel_size, center_xy=center_xy, facing_power=facing_power, fallback_color=fallback_color, allow_backface_fallback=allow_backface_fallback, visibility_tester=active_visibility_tester, blend_config=resolved_blend_config)
        vertex_colors[vertex.index] = result.color
        accepted_samples += result.accepted_samples
        rejected_samples += result.rejected_samples
        candidate_samples += result.candidate_samples
        source_rejected_samples += result.source_rejected_samples
        visible_samples += result.visible_samples
        occluded_samples += result.occluded_samples
        front_facing_samples += result.front_facing_samples
        backface_samples += result.backface_samples
        grazing_rejected_samples += result.grazing_rejected_samples
        relative_rejected_samples += result.relative_rejected_samples
        top_k_rejected_samples += result.top_k_rejected_samples
        selected_samples += result.selected_samples
        if result.used_fallback:
            fallback_vertices += 1
            if result.selected_samples > 0:
                projected_fallback_vertices += 1
            else:
                neutral_fallback_vertices += 1
        else:
            projected_vertices += 1
    color_attribute = _ensure_color_attribute(mesh, attribute_name=attribute_name)
    corner_colors = array('f')
    for loop in mesh.loops:
        color = vertex_colors[loop.vertex_index]
        corner_colors.extend(color)
    expected_float_count = loop_count * 4
    if len(corner_colors) != expected_float_count:
        raise RuntimeError('Projected color buffer size mismatch.')
    color_attribute.data.foreach_set('color', corner_colors)
    material = ensure_projected_material(attribute_name=attribute_name, material_name=material_name)
    if replace_materials:
        mesh.materials.clear()
    material_names = {item.name for item in mesh.materials if item is not None}
    if material.name not in material_names:
        mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.material_index = 0
    mesh.update()
    obj['bpt_material'] = MATERIAL_MODE
    obj['bpt_material_views'] = len(views)
    obj['bpt_material_attribute'] = attribute_name
    obj['bpt_material_projected_vertices'] = projected_vertices
    obj['bpt_material_fallback_vertices'] = fallback_vertices
    obj['bpt_material_projected_fallback_vertices'] = projected_fallback_vertices
    obj['bpt_material_neutral_fallback_vertices'] = neutral_fallback_vertices
    obj['bpt_material_visibility'] = active_visibility_tester is not None
    obj['bpt_material_visibility_mode'] = VISIBILITY_MODE if active_visibility_tester is not None else 'disabled'
    if active_visibility_tester is not None:
        obj['bpt_material_visibility_epsilon'] = active_visibility_tester.surface_epsilon
        obj['bpt_material_visibility_max_distance'] = active_visibility_tester.max_distance
    obj['bpt_material_blend_mode'] = BLEND_MODE
    obj['bpt_material_blend_min_facing'] = resolved_blend_config.min_facing
    obj['bpt_material_blend_facing_power'] = resolved_blend_config.facing_power
    obj['bpt_material_blend_relative_score_cutoff'] = resolved_blend_config.relative_score_cutoff
    obj['bpt_material_blend_max_contributors'] = resolved_blend_config.max_contributors
    obj['bpt_material_blend_weight_power'] = resolved_blend_config.weight_power
    obj['bpt_material_accepted_samples'] = accepted_samples
    obj['bpt_material_rejected_samples'] = rejected_samples
    obj['bpt_material_candidate_samples'] = candidate_samples
    obj['bpt_material_source_rejected_samples'] = source_rejected_samples
    obj['bpt_material_visible_samples'] = visible_samples
    obj['bpt_material_occluded_samples'] = occluded_samples
    obj['bpt_material_front_facing_samples'] = front_facing_samples
    obj['bpt_material_backface_samples'] = backface_samples
    obj['bpt_material_grazing_rejected_samples'] = grazing_rejected_samples
    obj['bpt_material_relative_rejected_samples'] = relative_rejected_samples
    obj['bpt_material_top_k_rejected_samples'] = top_k_rejected_samples
    obj['bpt_material_selected_samples'] = selected_samples
    return MaterialProjectionStats(vertex_count=vertex_count, loop_count=loop_count, view_count=len(views), projected_vertices=projected_vertices, fallback_vertices=fallback_vertices, rejected_samples=rejected_samples, accepted_samples=accepted_samples, candidate_samples=candidate_samples, source_rejected_samples=source_rejected_samples, visible_samples=visible_samples, occluded_samples=occluded_samples, front_facing_samples=front_facing_samples, backface_samples=backface_samples, grazing_rejected_samples=grazing_rejected_samples, relative_rejected_samples=relative_rejected_samples, top_k_rejected_samples=top_k_rejected_samples, selected_samples=selected_samples, projected_fallback_vertices=projected_fallback_vertices, neutral_fallback_vertices=neutral_fallback_vertices)
