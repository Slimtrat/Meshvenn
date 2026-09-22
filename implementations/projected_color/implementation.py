from __future__ import annotations
from ...core.geometry_contracts import require_geometry_surface_output
from ...core.pipeline_contracts import ImplementationAvailability, ImplementationDescriptor, PipelineContext, PipelineStage, StageExecutionResult
from ...core.projected_material import BLEND_MODE, COLOR_ATTRIBUTE_NAME, MATERIAL_MODE, VISIBILITY_MODE, apply_projected_material
from .configuration import IMPLEMENTATION_ID, ProjectedColorOutput
from .configuration import _config_from_settings, _resolve_settings
from .geometry import _material_views_from_geometry, _validate_geometry
from .metadata import _stats_metrics, _write_material_metadata

class ProjectedColorImplementation:
    """
    Built-in MATERIAL implementation.

        GeometrySurfaceOutput
                ↓
        source.material_views
                ↓
        GeometryProjectionSpace
                ↓
        V1.1 visibility
                ↓
        V1.2 adaptive blend
                ↓
        Blender CORNER color attribute
                ↓
        ProjectedColorOutput

    The implementation does not know whether the surface was
    created by:

        Native Visual Hull
        SDF Reconstruction
        another future geometry engine

    The actual projection/blending algorithm remains in
    core/projected_material.py.
    """
    _descriptor = ImplementationDescriptor(identifier=IMPLEMENTATION_ID, stage=PipelineStage.MATERIAL, label='Projected Color V1.2', description='Project source images onto the generated mesh using visibility-aware adaptive multi-view blending.', version='1.2', experimental=False, supports_headless=True, capabilities=('projected-color', 'vertex-color', 'multi-view', 'visibility-raycast', 'adaptive-blend', 'top-k', 'grazing-rejection', 'generic-geometry', 'projection-space'))

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            geometry = require_geometry_surface_output(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable('Compatible GEOMETRY surface is unavailable.', details={'error': str(exc)})
        try:
            _validate_geometry(geometry)
            material_views = _material_views_from_geometry(geometry)
        except Exception as exc:
            return ImplementationAvailability.unavailable('Geometry is incompatible with Projected Color.', details={'geometry_implementation': geometry.implementation_id, 'error': str(exc)})
        settings = _resolve_settings(context)
        try:
            config = _config_from_settings(settings)
        except Exception as exc:
            return ImplementationAvailability.unavailable('Projected Color configuration is invalid.', details={'error': str(exc)})
        projection_space = geometry.projection_space
        return ImplementationAvailability.ready_state(details={'object': geometry.object_name, 'geometry_implementation': geometry.implementation_id, 'views': len(material_views), 'material_mode': MATERIAL_MODE, 'visibility_mode': VISIBILITY_MODE if config.enable_visibility else 'disabled', 'blend_mode': BLEND_MODE, 'projection_space': {'width': projection_space.width, 'depth': projection_space.depth, 'height': projection_space.height, 'voxel_size': projection_space.voxel_size, 'center_xy': projection_space.center_xy, 'convention': projection_space.convention.value}})

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            geometry = require_geometry_surface_output(context)
        except Exception as exc:
            return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'Compatible GEOMETRY surface is unavailable: {exc}')
        try:
            _validate_geometry(geometry)
            material_views = list(_material_views_from_geometry(geometry))
        except Exception as exc:
            return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'Geometry is incompatible with Projected Color: {exc}', metadata={'geometry_implementation': geometry.implementation_id})
        settings = _resolve_settings(context)
        try:
            config = _config_from_settings(settings)
        except Exception as exc:
            return StageExecutionResult.failed_result(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, message=f'Invalid Projected Color configuration: {exc}', metadata={'exception_type': type(exc).__name__})
        obj = geometry.blender_object
        projection_space = geometry.projection_space
        blend_config = config.to_blend_config()
        stats = apply_projected_material(obj, material_views, volume_width=projection_space.width, volume_depth=projection_space.depth, volume_height=projection_space.height, voxel_size=projection_space.voxel_size, center_xy=projection_space.center_xy, attribute_name=COLOR_ATTRIBUTE_NAME, facing_power=config.facing_power, allow_backface_fallback=config.allow_backface_fallback, enable_visibility=config.enable_visibility, blend_config=blend_config)
        effective_visibility_mode = VISIBILITY_MODE if config.enable_visibility else 'disabled'
        output = ProjectedColorOutput(blender_object=obj, geometry=geometry, stats=stats, config=config, material_mode=MATERIAL_MODE, visibility_mode=effective_visibility_mode, blend_mode=BLEND_MODE, color_attribute=COLOR_ATTRIBUTE_NAME)
        _write_material_metadata(obj, output=output)
        context.metadata['material_object_name'] = obj.name
        context.metadata['material_mode'] = MATERIAL_MODE
        context.metadata['material_visibility_mode'] = effective_visibility_mode
        context.metadata['material_blend_mode'] = BLEND_MODE
        context.metadata['material_geometry_implementation'] = geometry.implementation_id
        context.metadata['material_projection_convention'] = projection_space.convention.value
        context.metadata['material_selected_samples'] = stats.selected_samples
        context.metadata['material_fallback_vertices'] = stats.fallback_vertices
        return StageExecutionResult.succeeded(stage=PipelineStage.MATERIAL, implementation_id=IMPLEMENTATION_ID, payload=output, message=f'Projected material generated: {stats.projected_vertices} direct vertices, {stats.fallback_vertices} fallback vertices, {stats.selected_samples} selected samples.', metrics=_stats_metrics(stats), metadata={'object_name': obj.name, 'geometry_implementation': geometry.implementation_id, 'material_mode': MATERIAL_MODE, 'visibility_mode': effective_visibility_mode, 'blend_mode': BLEND_MODE, 'color_attribute': COLOR_ATTRIBUTE_NAME, 'projection_space': {'width': projection_space.width, 'depth': projection_space.depth, 'height': projection_space.height, 'voxel_size': projection_space.voxel_size, 'center_xy': projection_space.center_xy, 'convention': projection_space.convention.value}, 'configuration': {'enable_visibility': config.enable_visibility, 'allow_backface_fallback': config.allow_backface_fallback, 'min_facing': config.min_facing, 'facing_power': config.facing_power, 'relative_score_cutoff': config.relative_score_cutoff, 'max_contributors': config.max_contributors, 'weight_power': config.weight_power}})
