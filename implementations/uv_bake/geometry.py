from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any
import bpy
from ...core.geometry_contracts import GeometrySurfaceOutput, require_geometry_surface_output
from ...core.material_blend import MaterialBlendConfig
from ...core.material_visibility import MeshVisibilityTester
from ...core.pipeline_contracts import ImplementationAvailability, ImplementationDescriptor, PipelineContext, PipelineStage, StageExecutionResult
from ...core.projected_material import DEFAULT_FALLBACK_COLOR, blend_projected_color
from ...core.uv_bake import SurfaceColorSample, UVBakeConfig, UVBakeResult, UVBakeTriangle, UVBakeVertex, bake_uv_texture
from . import constants as _dependency_0
from . import config as _dependency_1
from . import diagnostics as _dependency_2
from . import settings as _dependency_3
for _dependency in (_dependency_0, _dependency_1, _dependency_2, _dependency_3):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

def _validate_geometry(geometry: GeometrySurfaceOutput) -> None:
    """
    Validate only requirements shared by generic surfaces.

    There must be no dependency here on:

        NativeVisualHullOutput
        NativeVolume
        NativeMesh
        SDF implementation details
    """
    obj = geometry.blender_object
    if obj is None:
        raise ValueError('Geometry object is missing.')
    if getattr(obj, 'type', None) != 'MESH':
        raise TypeError('UV Bake requires a mesh object.')
    mesh = getattr(obj, 'data', None)
    if mesh is None:
        raise ValueError('Geometry mesh data is missing.')
    mesh.update()
    if len(mesh.vertices) == 0:
        raise ValueError('Geometry contains no vertices.')
    if len(mesh.polygons) == 0:
        raise ValueError('Geometry contains no polygons.')
    if len(mesh.loops) == 0:
        raise ValueError('Geometry contains no loops.')
    projection_space = geometry.projection_space
    if projection_space.width <= 0 or projection_space.depth <= 0 or projection_space.height <= 0:
        raise ValueError('Geometry contains invalid projection-space dimensions.')
    if not math.isfinite(projection_space.voxel_size) or projection_space.voxel_size <= 0.0:
        raise ValueError('Geometry contains an invalid projection-space voxel size.')
    projection_space.as_projection_kwargs()
    _material_views_from_geometry(geometry)

def _ensure_named_uv_layer(mesh: bpy.types.Mesh, name: str):
    layer = mesh.uv_layers.get(name)
    if layer is None:
        layer = mesh.uv_layers.new(name=name, do_init=False)
    mesh.uv_layers.active = layer
    try:
        layer.active_render = True
    except Exception:
        pass
    return layer

def _restore_object_selection(view_layer, previous_active, previous_selected, previous_mode: str) -> None:
    try:
        current_active = view_layer.objects.active
        if current_active is not None and current_active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        pass
    for item in view_layer.objects:
        try:
            item.select_set(False)
        except Exception:
            pass
    for item in previous_selected:
        try:
            if item.name in view_layer.objects:
                item.select_set(True)
        except Exception:
            pass
    try:
        if previous_active is not None and previous_active.name in view_layer.objects:
            view_layer.objects.active = previous_active
            if previous_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=previous_mode)
    except Exception:
        pass

def _smart_project_uv(obj: bpy.types.Object, *, uv_layer_name: str, island_margin: float, angle_limit_degrees: float):
    """
    Create/rebuild the UV map using Blender Smart Project.

    `island_margin` is already expressed as the FRACTION
    expected by Blender.
    """
    mesh = obj.data
    view_layer = bpy.context.view_layer
    if view_layer is None:
        raise RuntimeError('No Blender view layer is available for UV unwrap.')
    previous_active = view_layer.objects.active
    previous_selected = tuple((item for item in view_layer.objects if item.select_get()))
    previous_mode = previous_active.mode if previous_active is not None else 'OBJECT'
    try:
        if previous_active is not None and previous_active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for item in view_layer.objects:
            try:
                item.select_set(False)
            except Exception:
                pass
        obj.select_set(True)
        view_layer.objects.active = obj
        uv_layer = _ensure_named_uv_layer(mesh, uv_layer_name)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        result = bpy.ops.uv.smart_project(angle_limit=math.radians(angle_limit_degrees), margin_method='FRACTION', island_margin=island_margin, area_weight=0.0, correct_aspect=True, scale_to_bounds=True)
        if 'FINISHED' not in result:
            raise RuntimeError(f'Blender Smart UV Project returned {result}.')
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh.update()
        resolved_layer = mesh.uv_layers.get(uv_layer.name)
        if resolved_layer is None:
            raise RuntimeError('Smart UV Project completed without a UV layer.')
        mesh.uv_layers.active = resolved_layer
        try:
            resolved_layer.active_render = True
        except Exception:
            pass
        return resolved_layer
    finally:
        _restore_object_selection(view_layer, previous_active, previous_selected, previous_mode)

def _resolve_uv_layer(obj: bpy.types.Object, config: UVBakeMaterialConfig):
    mesh = obj.data
    if config.reuse_existing_uv:
        layer = mesh.uv_layers.active
        if layer is None:
            raise ValueError('Reuse Existing UV is enabled but the mesh has no UV map.')
        try:
            layer.active_render = True
        except Exception:
            pass
        return layer
    return _smart_project_uv(obj, uv_layer_name=config.uv_layer_name, island_margin=config.effective_island_margin_fraction, angle_limit_degrees=config.angle_limit_degrees)
