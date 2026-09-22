from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Callable, TypeAlias
Vector3: TypeAlias = tuple[float, float, float]
DEFAULT_RELATIVE_EPSILON = 1e-05
DEFAULT_ABSOLUTE_EPSILON = 1e-06
DEFAULT_RAY_LENGTH_MULTIPLIER = 2.0
MIN_DIRECTION_LENGTH = 1e-12
MIN_RAY_DISTANCE = 1e-06

@dataclass(frozen=True)
class RaycastHit:
    """
    Backend-independent representation of one ray hit.

    `distance` is measured from the ray origin.

    `polygon_index` is optional because pure Python tests
    do not need to emulate Blender polygon identifiers.
    """
    distance: float
    polygon_index: int | None = None
    position: Vector3 | None = None
    normal: Vector3 | None = None
RaycastFunction: TypeAlias = Callable[[Vector3, Vector3, float], RaycastHit | None]

@dataclass(frozen=True)
class VisibilityConfig:
    """
    Numerical configuration for mesh visibility queries.

    relative_epsilon:
        Scale-relative surface offset.

        The effective epsilon is:

            max(
                absolute_epsilon,
                mesh_diagonal
                * relative_epsilon,
            )

    absolute_epsilon:
        Minimum offset even for very small meshes.

    ray_length_multiplier:
        Maximum ray distance expressed relative to the
        bounding-box diagonal.

        A value greater than 1 is sufficient for an
        orthographic visibility query because any
        occluding geometry must remain inside the mesh
        bounding box.
    """
    relative_epsilon: float = DEFAULT_RELATIVE_EPSILON
    absolute_epsilon: float = DEFAULT_ABSOLUTE_EPSILON
    ray_length_multiplier: float = DEFAULT_RAY_LENGTH_MULTIPLIER

    def validate(self) -> None:
        if not math.isfinite(self.relative_epsilon) or self.relative_epsilon < 0.0:
            raise ValueError('relative_epsilon must be finite and >= 0.')
        if not math.isfinite(self.absolute_epsilon) or self.absolute_epsilon <= 0.0:
            raise ValueError('absolute_epsilon must be finite and > 0.')
        if not math.isfinite(self.ray_length_multiplier) or self.ray_length_multiplier <= 1.0:
            raise ValueError('ray_length_multiplier must be finite and > 1.')

@dataclass(frozen=True)
class VisibilityResult:
    """
    Result of one surface -> camera visibility test.
    """
    visible: bool
    occluded: bool
    hit_distance: float | None = None
    polygon_index: int | None = None

    @classmethod
    def clear(cls) -> 'VisibilityResult':
        return cls(visible=True, occluded=False, hit_distance=None, polygon_index=None)

    @classmethod
    def blocked(cls, hit: RaycastHit) -> 'VisibilityResult':
        return cls(visible=False, occluded=True, hit_distance=float(hit.distance), polygon_index=hit.polygon_index)

def _vector_length(value: Vector3) -> float:
    return math.sqrt(float(value[0]) ** 2 + float(value[1]) ** 2 + float(value[2]) ** 2)

def _normalize(value: Vector3) -> Vector3:
    length = _vector_length(value)
    if not math.isfinite(length) or length <= MIN_DIRECTION_LENGTH:
        raise ValueError('Visibility ray direction must be a finite, non-zero vector.')
    inverse = 1.0 / length
    result = (float(value[0]) * inverse, float(value[1]) * inverse, float(value[2]) * inverse)
    if not all((math.isfinite(component) for component in result)):
        raise ValueError('Visibility ray direction contains non-finite values.')
    return result

def _offset_point(position: Vector3, direction: Vector3, distance: float) -> Vector3:
    return (float(position[0]) + direction[0] * distance, float(position[1]) + direction[1] * distance, float(position[2]) + direction[2] * distance)

def _validate_position(position: Vector3) -> Vector3:
    result = (float(position[0]), float(position[1]), float(position[2]))
    if not all((math.isfinite(component) for component in result)):
        raise ValueError('Visibility position contains non-finite values.')
    return result

def bounding_box_diagonal(vertices: list[Vector3]) -> float:
    """
    Return the diagonal of an axis-aligned bounding box.
    """
    if not vertices:
        raise ValueError('Cannot compute visibility bounds for an empty vertex list.')
    first = _validate_position(vertices[0])
    minimum_x = first[0]
    minimum_y = first[1]
    minimum_z = first[2]
    maximum_x = first[0]
    maximum_y = first[1]
    maximum_z = first[2]
    for vertex in vertices[1:]:
        x, y, z = _validate_position(vertex)
        minimum_x = min(minimum_x, x)
        minimum_y = min(minimum_y, y)
        minimum_z = min(minimum_z, z)
        maximum_x = max(maximum_x, x)
        maximum_y = max(maximum_y, y)
        maximum_z = max(maximum_z, z)
    delta_x = maximum_x - minimum_x
    delta_y = maximum_y - minimum_y
    delta_z = maximum_z - minimum_z
    return math.sqrt(delta_x * delta_x + delta_y * delta_y + delta_z * delta_z)

def compute_surface_epsilon(mesh_diagonal: float, config: VisibilityConfig) -> float:
    config.validate()
    diagonal = float(mesh_diagonal)
    if not math.isfinite(diagonal) or diagonal < 0.0:
        raise ValueError('mesh_diagonal must be finite and >= 0.')
    return max(config.absolute_epsilon, diagonal * config.relative_epsilon)

def compute_ray_distance(mesh_diagonal: float, surface_epsilon: float, config: VisibilityConfig) -> float:
    config.validate()
    diagonal = float(mesh_diagonal)
    epsilon = float(surface_epsilon)
    if not math.isfinite(diagonal) or diagonal < 0.0:
        raise ValueError('mesh_diagonal must be finite and >= 0.')
    if not math.isfinite(epsilon) or epsilon <= 0.0:
        raise ValueError('surface_epsilon must be finite and > 0.')
    return max(diagonal * config.ray_length_multiplier, epsilon * 10.0, MIN_RAY_DISTANCE)
