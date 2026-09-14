from __future__ import annotations
import math
from typing import Any
from ...core.geometry_contracts import GeometrySurfaceOutput

def _material_views_from_geometry(geometry: GeometrySurfaceOutput) -> tuple[Any, ...]:
    """
    Resolve projection-material views from the INPUT source
    without requiring ProjectionImagesOutput.

    This is intentionally capability-based.

    Projected Color needs:

        geometry.source.material_views

    It does NOT need to know the concrete INPUT or GEOMETRY
    class which supplied them.

    A future input implementation can therefore participate
    simply by exposing a compatible material_views sequence.
    """
    source = geometry.source
    material_views = getattr(source, 'material_views', None)
    if material_views is None:
        raise TypeError('GEOMETRY source does not expose material_views required by Projected Color.')
    try:
        resolved = tuple(material_views)
    except TypeError as exc:
        raise TypeError('GEOMETRY source material_views is not iterable.') from exc
    if not resolved:
        raise ValueError('No material projection views are available.')
    return resolved

def _validate_geometry(geometry: GeometrySurfaceOutput) -> None:
    """
    Validate only the generic surface requirements needed by
    Projected Color.

    There must be no knowledge of:

        NativeVolume
        NativeMesh
        Visual Hull
        SDF internals
    """
    obj = geometry.blender_object
    if obj is None:
        raise ValueError('Geometry has no Blender object.')
    if getattr(obj, 'type', None) != 'MESH':
        raise TypeError('Projected Color requires a mesh object.')
    mesh = getattr(obj, 'data', None)
    if mesh is None:
        raise ValueError('Geometry object has no mesh data.')
    if len(mesh.vertices) == 0:
        raise ValueError('Geometry mesh contains no vertices.')
    if len(mesh.polygons) == 0:
        raise ValueError('Geometry mesh contains no polygons.')
    if len(mesh.loops) == 0:
        raise ValueError('Geometry mesh contains no loops.')
    projection_space = geometry.projection_space
    if projection_space.width <= 0 or projection_space.depth <= 0 or projection_space.height <= 0:
        raise ValueError('Geometry contains invalid projection-space dimensions.')
    if not math.isfinite(projection_space.voxel_size) or projection_space.voxel_size <= 0.0:
        raise ValueError('Geometry contains an invalid projection-space voxel size.')
    projection_space.as_projection_kwargs()
    _material_views_from_geometry(geometry)
