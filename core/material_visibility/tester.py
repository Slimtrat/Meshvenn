from __future__ import annotations
import importlib
import math
from typing import Any
from .domain import MIN_RAY_DISTANCE, RaycastFunction, Vector3, VisibilityConfig, VisibilityResult
from .domain import _normalize, _offset_point, _validate_position, bounding_box_diagonal, compute_ray_distance, compute_surface_epsilon

class MeshVisibilityTester:
    """
    Orthographic surface visibility tester.

    The projection system does not use perspective cameras.
    Every source view has one constant camera direction.

    For a surface point P and a direction D pointing from
    the object toward the camera:

        P
        |
        | offset epsilon
        v
        P' -----------------------> camera
                    D

    If another polygon is intersected after P', then P is
    hidden from that source view.

    The tiny offset is essential because P lies directly on
    the source mesh and would otherwise frequently intersect
    its own triangle due to floating-point precision.

    This class intentionally has no hard Blender dependency.
    Tests can provide any `raycast` callback.

    Blender-specific construction is provided by
    `from_blender_object()`.
    """

    def __init__(self, raycast: RaycastFunction, *, surface_epsilon: float, max_distance: float) -> None:
        epsilon = float(surface_epsilon)
        distance = float(max_distance)
        if not math.isfinite(epsilon) or epsilon <= 0.0:
            raise ValueError('surface_epsilon must be finite and > 0.')
        if not math.isfinite(distance) or distance <= epsilon:
            raise ValueError('max_distance must be finite and greater than surface_epsilon.')
        if not callable(raycast):
            raise TypeError('raycast must be callable.')
        self._raycast = raycast
        self.surface_epsilon = epsilon
        self.max_distance = distance

    def query(self, position: Vector3, camera_direction: Vector3) -> VisibilityResult:
        """
        Test whether `position` is directly visible from one
        orthographic source camera.

        `camera_direction` MUST point from the object toward
        the camera.

        Example:

            azimuth 0°
                camera on -Y

                direction = (0, -1, 0)

        A clear ray means the candidate source projection is
        allowed to contribute color.

        Any mesh intersection between the surface point and
        the camera rejects that candidate.
        """
        position = _validate_position(position)
        direction = _normalize(camera_direction)
        origin = _offset_point(position, direction, self.surface_epsilon)
        ray_distance = self.max_distance - self.surface_epsilon
        if ray_distance <= MIN_RAY_DISTANCE:
            return VisibilityResult.clear()
        hit = self._raycast(origin, direction, ray_distance)
        if hit is None:
            return VisibilityResult.clear()
        hit_distance = float(hit.distance)
        if not math.isfinite(hit_distance) or hit_distance < 0.0:
            raise ValueError('Raycast backend returned an invalid hit distance.')
        if hit_distance <= self.surface_epsilon:
            return VisibilityResult.clear()
        if hit_distance > ray_distance:
            return VisibilityResult.clear()
        return VisibilityResult.blocked(hit)

    def is_visible(self, position: Vector3, camera_direction: Vector3) -> bool:
        return self.query(position, camera_direction).visible

    @classmethod
    def from_blender_object(cls, obj: Any, *, config: VisibilityConfig | None=None) -> 'MeshVisibilityTester':
        """
        Build a BVH directly from a Blender mesh object.

        The BVH is intentionally built in MESH LOCAL SPACE.

        This matches projected_material.py, which projects
        `vertex.co` before object normalization/scaling.

        Do not build this tester after changing the mesh
        coordinates unless the material projection uses the
        same transformed coordinates.
        """
        if config is None:
            config = VisibilityConfig()
        config.validate()
        if obj is None:
            raise TypeError('Visibility target object cannot be None.')
        object_type = getattr(obj, 'type', None)
        if object_type != 'MESH':
            raise TypeError('Visibility target must be a mesh object.')
        mesh = getattr(obj, 'data', None)
        if mesh is None:
            raise TypeError('Mesh object has no mesh data.')
        mesh.update()
        vertices: list[Vector3] = []
        for vertex in mesh.vertices:
            vertices.append((float(vertex.co.x), float(vertex.co.y), float(vertex.co.z)))
        if not vertices:
            raise ValueError('Cannot build visibility BVH from an empty mesh.')
        polygons: list[tuple[int, ...]] = []
        for polygon in mesh.polygons:
            indices = tuple((int(index) for index in polygon.vertices))
            if len(indices) < 3:
                continue
            polygons.append(indices)
        if not polygons:
            raise ValueError('Cannot build visibility BVH from a mesh without polygons.')
        diagonal = bounding_box_diagonal(vertices)
        surface_epsilon = compute_surface_epsilon(diagonal, config)
        max_distance = compute_ray_distance(diagonal, surface_epsilon, config)
        raycast = importlib.import_module(__package__)._build_blender_bvh_raycast(vertices, polygons)
        return cls(raycast, surface_epsilon=surface_epsilon, max_distance=max_distance)
