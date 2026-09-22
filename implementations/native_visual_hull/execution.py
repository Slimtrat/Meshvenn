from __future__ import annotations
import bpy
from ...core.native_bridge import NativeCore
from ...core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..projection_images import require_projection_images_output
from .availability import _native_library_availability
from .blender_output import (
    _apply_non_destructive_height_normalization,
    _remove_blender_object,
    _write_geometry_metadata,
)
from .config import (
    _config_from_settings,
    _projection_space_from_volume,
    _resolve_settings,
)
from .constants import DEFAULT_MESH_NAME, DEFAULT_OBJECT_NAME, IMPLEMENTATION_ID
from .output import NativeVisualHullOutput


def execute_native_visual_hull(context: PipelineContext) -> StageExecutionResult:
    settings = _resolve_settings(context)
    if settings is None:
        return StageExecutionResult.failed_result(
            stage=PipelineStage.GEOMETRY,
            implementation_id=IMPLEMENTATION_ID,
            message="Meshvenn settings are unavailable.",
        )
    try:
        source = require_projection_images_output(context)
    except Exception as exc:
        return StageExecutionResult.failed_result(
            stage=PipelineStage.GEOMETRY,
            implementation_id=IMPLEMENTATION_ID,
            message=f"Prepared projection input is unavailable: {exc}",
        )
    if source.projection_count < 2:
        return StageExecutionResult.failed_result(
            stage=PipelineStage.GEOMETRY,
            implementation_id=IMPLEMENTATION_ID,
            message="At least two prepared projections are required.",
            metadata={"projection_count": source.projection_count},
        )
    try:
        config = _config_from_settings(settings)
    except Exception as exc:
        return StageExecutionResult.failed_result(
            stage=PipelineStage.GEOMETRY,
            implementation_id=IMPLEMENTATION_ID,
            message=f"Invalid Native Visual Hull configuration: {exc}",
            metadata={"exception_type": type(exc).__name__},
        )
    obj: bpy.types.Object | None = None
    try:
        core = NativeCore()
        volume = core.build_visual_hull(
            source.native_projections,
            resolution=config.resolution,
            symmetry_x=config.symmetry_x,
            thread_count=config.thread_count,
        )
        if volume.occupied_count == 0:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.GEOMETRY,
                implementation_id=IMPLEMENTATION_ID,
                message="The projections produced an empty visual hull.",
                metadata={
                    "projection_count": source.projection_count,
                    "empty_masks": source.empty_mask_count,
                    "resolution": config.resolution,
                },
            )
        native_mesh = core.build_surface_mesh(
            volume,
            voxel_size=config.voxel_size,
            center_xy=config.center_xy,
            mesh_mode=config.mesh_mode,
        )
        if native_mesh.vertex_count <= 0:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.GEOMETRY,
                implementation_id=IMPLEMENTATION_ID,
                message="Native mesh extraction returned no vertices.",
                metadata={
                    "occupied_voxels": volume.occupied_count,
                    "mesh_mode": config.mesh_mode,
                },
            )
        if native_mesh.polygon_count <= 0:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.GEOMETRY,
                implementation_id=IMPLEMENTATION_ID,
                message="Native mesh extraction returned no polygons.",
                metadata={
                    "vertices": native_mesh.vertex_count,
                    "mesh_mode": config.mesh_mode,
                },
            )
        obj = create_blender_mesh_from_native(
            native_mesh, mesh_name=DEFAULT_MESH_NAME, object_name=DEFAULT_OBJECT_NAME
        )
        shade_smooth_native_object(obj)
        projection_space = _projection_space_from_volume(volume, config)
        normalization_scale = _apply_non_destructive_height_normalization(
            obj, enabled=config.normalize_height, target_height=config.target_height
        )
        _write_geometry_metadata(
            obj,
            source=source,
            volume=volume,
            native_mesh=native_mesh,
            projection_space=projection_space,
            config=config,
            normalization_scale=normalization_scale,
        )
        output_metrics = {
            "projection_count": source.projection_count,
            "resolution": config.resolution,
            "occupied_voxels": volume.occupied_count,
            "vertex_count": native_mesh.vertex_count,
            "index_count": native_mesh.index_count,
            "polygon_count": native_mesh.polygon_count,
            "normalization_scale": normalization_scale,
        }
        output_metadata = {
            "mesh_mode": config.mesh_mode,
            "symmetry_x": config.symmetry_x,
            "thread_count": config.thread_count,
            "normalized_height": config.normalize_height,
            "target_height": config.target_height if config.normalize_height else None,
            "native_local_coordinates_preserved": True,
            "projection_convention": projection_space.convention.value,
        }
        output = NativeVisualHullOutput(
            blender_object=obj,
            source=source,
            projection_space=projection_space,
            volume=volume,
            native_mesh=native_mesh,
            resolution=config.resolution,
            symmetry_x=config.symmetry_x,
            thread_count=config.thread_count,
            mesh_mode=config.mesh_mode,
            normalized_height=config.normalize_height,
            target_height=config.target_height if config.normalize_height else None,
            normalization_scale=normalization_scale,
            metrics=output_metrics,
            metadata=output_metadata,
        )
        context.metadata["geometry_object_name"] = obj.name
        context.metadata["geometry_implementation"] = IMPLEMENTATION_ID
        context.metadata["geometry_contract"] = "surface-output-v1"
        context.metadata["geometry_mesh_mode"] = config.mesh_mode
        context.metadata["geometry_occupied_voxels"] = volume.occupied_count
        context.metadata["geometry_projection_space"] = {
            "width": projection_space.width,
            "depth": projection_space.depth,
            "height": projection_space.height,
            "voxel_size": projection_space.voxel_size,
            "center_xy": projection_space.center_xy,
            "convention": projection_space.convention.value,
        }
        created_object = obj
        return StageExecutionResult.succeeded(
            stage=PipelineStage.GEOMETRY,
            implementation_id=IMPLEMENTATION_ID,
            payload=output,
            message=f"Native visual hull generated: {volume.occupied_count} voxels, {native_mesh.vertex_count} vertices, {native_mesh.polygon_count} polygons.",
            metrics={
                "projections": source.projection_count,
                "resolution": config.resolution,
                "occupied_voxels": volume.occupied_count,
                "vertices": native_mesh.vertex_count,
                "indices": native_mesh.index_count,
                "polygons": native_mesh.polygon_count,
                "normalization_scale": normalization_scale,
            },
            metadata={
                "object_name": created_object.name,
                "mesh_name": created_object.data.name,
                "geometry_contract": "surface-output-v1",
                "mesh_mode": config.mesh_mode,
                "voxel_size": projection_space.voxel_size,
                "center_xy": projection_space.center_xy,
                "symmetry_x": config.symmetry_x,
                "thread_count": config.thread_count,
                "projection_space": {
                    "width": projection_space.width,
                    "depth": projection_space.depth,
                    "height": projection_space.height,
                    "voxel_size": projection_space.voxel_size,
                    "center_xy": projection_space.center_xy,
                    "convention": projection_space.convention.value,
                },
                "volume": {
                    "width": volume.width,
                    "depth": volume.depth,
                    "height": volume.height,
                    "bounds": (
                        list(volume.bounds) if volume.bounds is not None else None
                    ),
                },
                "normalize_height": config.normalize_height,
                "target_height": (
                    config.target_height if config.normalize_height else None
                ),
                "native_local_coordinates_preserved": True,
            },
        )
    except Exception:
        _remove_blender_object(obj)
        raise
