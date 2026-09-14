from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Any
import bpy
from ..core.geometry_contracts import GeometrySurfaceOutput, require_geometry_surface_output
from ..core.material_blend import MaterialBlendConfig
from ..core.material_visibility import MeshVisibilityTester
from ..core.pipeline_contracts import ImplementationAvailability, ImplementationDescriptor, PipelineContext, PipelineStage, StageExecutionResult
from ..core.projected_material import DEFAULT_FALLBACK_COLOR, blend_projected_color
from ..core.uv_bake import SurfaceColorSample, UVBakeConfig, UVBakeResult, UVBakeTriangle, UVBakeVertex, bake_uv_texture
from . import constants as _dependency_0
from . import config as _dependency_1
from . import diagnostics as _dependency_2
from . import settings as _dependency_3
from . import geometry as _dependency_4
from . import triangles as _dependency_5
from . import sampler as _dependency_6
from . import assets as _dependency_7
from . import metadata as _dependency_8
from . import ui as _dependency_9
for _dependency in (_dependency_0, _dependency_1, _dependency_2, _dependency_3, _dependency_4, _dependency_5, _dependency_6, _dependency_7, _dependency_8, _dependency_9):
    globals().update({name: value for name, value in vars(_dependency).items() if not name.startswith('__')})
del _dependency

def execute_uv_bake(self, context: PipelineContext) -> StageExecutionResult:
    settings = _resolve_settings(context)
    try:
        geometry = require_geometry_surface_output(context)
    except Exception as exc:
        return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'Compatible GEOMETRY surface is unavailable: {exc}')
    try:
        _validate_geometry(geometry)
        material_views = _material_views_from_geometry(geometry)
        config = _config_from_settings(settings)
    except Exception as exc:
        return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'Geometry or UV Bake V2 configuration is invalid: {exc}', metadata={'geometry_implementation': geometry.implementation_id})
    obj = geometry.blender_object
    projection_space = geometry.projection_space
    try:
        uv_layer = _resolve_uv_layer(obj, config)
    except Exception as exc:
        return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'UV unwrap failed: {exc}', metadata={'geometry_implementation': geometry.implementation_id, 'requested_island_margin': config.island_margin, 'effective_island_margin': config.effective_island_margin_fraction, 'effective_island_margin_pixels': config.effective_island_margin_pixels})
    try:
        triangles = _build_uv_triangles(obj, uv_layer)
        layout = _uv_layout_diagnostics(triangles, texture_size=config.texture_size)
    except Exception as exc:
        return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'UV triangulation failed: {exc}', metadata={'geometry_implementation': geometry.implementation_id})
    try:
        sampler = _build_surface_sampler(geometry, config)
    except Exception as exc:
        return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'Surface sampler creation failed: {exc}', metadata={'geometry_implementation': geometry.implementation_id})
    window_manager = getattr(bpy.context, 'window_manager', None)
    if window_manager is not None:
        try:
            window_manager.progress_begin(0, len(triangles))
        except Exception:
            window_manager = None

    def progress_callback(progress) -> None:
        if window_manager is None:
            return
        try:
            window_manager.progress_update(progress.completed_triangles)
        except Exception:
            pass
    try:
        try:
            bake_result = bake_uv_texture(triangles, sampler, config=config.to_bake_config(), progress_callback=progress_callback)
        except Exception as exc:
            return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'UV rasterization failed: {exc}', metadata={'geometry_implementation': geometry.implementation_id, 'triangles': len(triangles), 'total_uv_area': layout.total_uv_area, 'total_uv_area_pixels': layout.total_texture_area_pixels, 'mean_triangle_area_pixels': layout.mean_triangle_area_pixels, 'subpixel_triangle_ratio': layout.subpixel_triangle_ratio})
    finally:
        if window_manager is not None:
            try:
                window_manager.progress_end()
            except Exception:
                pass
    stats = bake_result.stats
    if stats.covered_pixels <= 0:
        return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message='UV bake produced no covered texels.', metadata={'geometry_implementation': geometry.implementation_id, 'triangles': len(triangles), 'texture_size': config.texture_size, 'requested_island_margin': config.island_margin, 'effective_island_margin': config.effective_island_margin_fraction, 'effective_island_margin_pixels': config.effective_island_margin_pixels, 'total_uv_area': layout.total_uv_area, 'total_uv_area_pixels': layout.total_texture_area_pixels, 'minimum_triangle_area_pixels': layout.minimum_triangle_area_pixels, 'mean_triangle_area_pixels': layout.mean_triangle_area_pixels, 'maximum_triangle_area_pixels': layout.maximum_triangle_area_pixels, 'subpixel_triangle_count': layout.subpixel_triangle_count, 'subpixel_triangle_ratio': layout.subpixel_triangle_ratio})
    try:
        image = _create_baked_image(obj, bake_result)
    except Exception as exc:
        return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'Could not create baked Blender image: {exc}', metadata={'geometry_implementation': geometry.implementation_id})
    material = None
    try:
        material = _create_baked_material(obj, image=image, uv_layer_name=uv_layer.name)
        _assign_material(obj, material)
        output = UVBakeMaterialOutput(blender_object=obj, geometry=geometry, image=image, material=material, uv_layer_name=uv_layer.name, bake_result=bake_result, config=config)
        _write_metadata(obj, output, layout=layout)
    except Exception:
        if material is not None and material.users == 0:
            bpy.data.materials.remove(material)
        if image.users == 0:
            bpy.data.images.remove(image)
        raise
    context.metadata['material_mode'] = MATERIAL_MODE
    context.metadata['material_geometry_implementation'] = geometry.implementation_id
    context.metadata['material_projection_convention'] = projection_space.convention.value
    context.metadata['uv_bake_image'] = image.name
    context.metadata['uv_bake_material'] = material.name
    context.metadata['uv_bake_effective_island_margin'] = config.effective_island_margin_fraction
    return StageExecutionResult.succeeded(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, payload=output, message=f'UV texture baked: {config.texture_size}×{config.texture_size}, {stats.covered_pixels} covered texels.', metrics={'triangles': stats.triangle_count, 'rasterized_triangles': stats.rasterized_triangles, 'degenerate_triangles': stats.degenerate_triangles, 'texture_size': config.texture_size, 'covered_pixels': stats.covered_pixels, 'padded_pixels': stats.padded_pixels, 'overlap_pixels': stats.overlap_pixels, 'surface_samples': stats.surface_samples, 'fallback_samples': stats.fallback_samples, 'selected_source_samples': stats.selected_source_samples, 'coverage_ratio': stats.coverage_ratio, 'uv_total_area': layout.total_uv_area, 'uv_total_area_pixels': layout.total_texture_area_pixels, 'uv_min_triangle_area_pixels': layout.minimum_triangle_area_pixels, 'uv_mean_triangle_area_pixels': layout.mean_triangle_area_pixels, 'uv_max_triangle_area_pixels': layout.maximum_triangle_area_pixels, 'uv_subpixel_triangles': layout.subpixel_triangle_count, 'uv_subpixel_triangle_ratio': layout.subpixel_triangle_ratio}, metadata={'object_name': obj.name, 'geometry_implementation': geometry.implementation_id, 'image_name': image.name, 'material_name': material.name, 'uv_layer': uv_layer.name, 'texture_width': bake_result.texture.width, 'texture_height': bake_result.texture.height, 'padding_pixels': config.padding_pixels, 'samples_per_axis': config.samples_per_axis, 'visibility': config.enable_visibility, 'reuse_existing_uv': config.reuse_existing_uv, 'requested_island_margin': config.island_margin, 'effective_island_margin': config.effective_island_margin_fraction, 'effective_island_margin_pixels': config.effective_island_margin_pixels, 'projection_space': {'width': projection_space.width, 'depth': projection_space.depth, 'height': projection_space.height, 'voxel_size': projection_space.voxel_size, 'center_xy': projection_space.center_xy, 'convention': projection_space.convention.value}})
