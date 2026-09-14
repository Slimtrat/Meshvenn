from __future__ import annotations

import math
import bpy

from ...core.geometry_contracts import GeometryProjectionSpace
from ...core.native_bridge import NativeMesh, NativeVolume
from ..projection_images import ProjectionImagesOutput
from .config import NativeVisualHullConfig
from .constants import IMPLEMENTATION_ID


def _remove_blender_object(obj: bpy.types.Object | None) -> None:
    """
    Remove a partially-created geometry object when the
    implementation fails after Blender injection.
    """
    if obj is None:
        return
    mesh = obj.data if obj.type == "MESH" and obj.data is not None else None
    try:
        bpy.data.objects.remove(obj, do_unlink=True)
    finally:
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _apply_non_destructive_height_normalization(
    obj: bpy.types.Object, *, enabled: bool, target_height: float
) -> float:
    """
    Normalize visible object height without altering local
    mesh coordinates.

    Why object.scale instead of obj.data.transform():

        projection-dependent MATERIAL stages work in the
        reconstruction coordinate space.

    GEOMETRY runs before MATERIAL, therefore applying scale
    directly to vertex coordinates here would invalidate
    projection.

    Uniform object scale preserves:

        vertex.co
        native BVH coordinates
        GeometryProjectionSpace

    while presenting the requested final size in Blender.

    RIG / EXPORT may apply the transform later once
    projection-dependent stages are complete.
    """
    if not enabled:
        return 1.0
    if not math.isfinite(target_height) or target_height <= 0.0:
        raise ValueError("Target height must be finite and greater than zero.")
    current_height = float(obj.dimensions.z)
    if not math.isfinite(current_height) or current_height <= 0.0:
        return 1.0
    factor = target_height / current_height
    obj.scale.x *= factor
    obj.scale.y *= factor
    obj.scale.z *= factor
    if bpy.context.view_layer is not None:
        bpy.context.view_layer.update()
    return float(factor)


def _write_geometry_metadata(
    obj: bpy.types.Object,
    *,
    source: ProjectionImagesOutput,
    volume: NativeVolume,
    native_mesh: NativeMesh,
    projection_space: GeometryProjectionSpace,
    config: NativeVisualHullConfig,
    normalization_scale: float,
) -> None:
    """
    Preserve historical BPT metadata while exposing the new
    generic GEOMETRY contract identity.
    """
    obj["meshvenn_geometry_implementation"] = IMPLEMENTATION_ID
    obj["meshvenn_geometry_version"] = "1"
    obj["meshvenn_native_space_preserved"] = True
    obj["meshvenn_normalization_scale"] = float(normalization_scale)
    obj["meshvenn_projection_convention"] = projection_space.convention.value
    obj["meshvenn_projection_width"] = projection_space.width
    obj["meshvenn_projection_depth"] = projection_space.depth
    obj["meshvenn_projection_height"] = projection_space.height
    obj["meshvenn_projection_voxel_size"] = projection_space.voxel_size
    obj["meshvenn_projection_center_xy"] = projection_space.center_xy
    obj["bpt_engine"] = "native-cpp"
    obj["bpt_mesh_mode"] = config.mesh_mode
    obj["bpt_projection_count"] = source.projection_count
    obj["bpt_resolution"] = config.resolution
    obj["bpt_threads"] = config.thread_count
    obj["bpt_symmetry_x"] = config.symmetry_x
    obj["bpt_voxel_size"] = config.voxel_size
    obj["bpt_center_xy"] = config.center_xy
    obj["bpt_occupied_voxels"] = volume.occupied_count
    obj["bpt_native_vertices"] = native_mesh.vertex_count
    obj["bpt_native_polygons"] = native_mesh.polygon_count
    obj["bpt_native_indices"] = native_mesh.index_count
    obj["bpt_normalize_height"] = config.normalize_height
    if config.normalize_height:
        obj["bpt_target_height"] = config.target_height
