from __future__ import annotations
from .domain import RaycastFunction, RaycastHit, Vector3

def _build_blender_bvh_raycast(vertices: list[Vector3], polygons: list[tuple[int, ...]]) -> RaycastFunction:
    """
    Create a Blender BVHTree-backed callback.

    Importing mathutils happens here rather than at module
    import time so this module remains usable by normal
    Python unit tests.
    """
    try:
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
    except ImportError as exc:
        raise RuntimeError('Blender mathutils is required to build mesh visibility.') from exc
    blender_vertices = [Vector((vertex[0], vertex[1], vertex[2])) for vertex in vertices]
    bvh = BVHTree.FromPolygons(blender_vertices, polygons, all_triangles=False, epsilon=0.0)
    if bvh is None:
        raise RuntimeError('Blender failed to build the visibility BVH.')

    def raycast(origin: Vector3, direction: Vector3, distance: float) -> RaycastHit | None:
        blender_origin = Vector((origin[0], origin[1], origin[2]))
        blender_direction = Vector((direction[0], direction[1], direction[2]))
        hit_position, hit_normal, polygon_index, hit_distance = bvh.ray_cast(blender_origin, blender_direction, float(distance))
        if hit_position is None or hit_distance is None:
            return None
        position_tuple: Vector3 = (float(hit_position.x), float(hit_position.y), float(hit_position.z))
        normal_tuple: Vector3 | None
        if hit_normal is None:
            normal_tuple = None
        else:
            normal_tuple = (float(hit_normal.x), float(hit_normal.y), float(hit_normal.z))
        normalized_polygon_index: int | None
        if polygon_index is None:
            normalized_polygon_index = None
        else:
            normalized_polygon_index = int(polygon_index)
        return RaycastHit(distance=float(hit_distance), polygon_index=normalized_polygon_index, position=position_tuple, normal=normal_tuple)
    return raycast
