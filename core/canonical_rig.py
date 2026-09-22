"""Deterministic canonical biped fit and fallback skin weights.

The fit operates in mesh-local Blender coordinates: X is left/right and Z is up.
It deliberately makes no claim to infer anatomy from a silhouette-only mesh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class MeshBounds:
    minimum: Point3
    maximum: Point3

    def __post_init__(self) -> None:
        if len(self.minimum) != 3 or len(self.maximum) != 3:
            raise ValueError("Mesh bounds require three coordinates per corner.")
        if any(not math.isfinite(float(v)) for v in (*self.minimum, *self.maximum)):
            raise ValueError("Mesh bounds must be finite.")
        if any(hi <= lo for lo, hi in zip(self.minimum, self.maximum)):
            raise ValueError("Mesh bounds must have positive width, depth and height.")

    @property
    def center_x(self) -> float:
        return (self.minimum[0] + self.maximum[0]) * 0.5

    @property
    def center_y(self) -> float:
        return (self.minimum[1] + self.maximum[1]) * 0.5

    @property
    def width(self) -> float:
        return self.maximum[0] - self.minimum[0]

    @property
    def depth(self) -> float:
        return self.maximum[1] - self.minimum[1]

    @property
    def height(self) -> float:
        return self.maximum[2] - self.minimum[2]


@dataclass(frozen=True)
class BoneSpec:
    name: str
    parent: str | None
    head: Point3
    tail: Point3
    deform: bool = True

    def __post_init__(self) -> None:
        if not self.name or self.parent == self.name:
            raise ValueError("Bone names and parent relationships must be valid.")
        if any(not math.isfinite(float(v)) for v in (*self.head, *self.tail)):
            raise ValueError("Bone coordinates must be finite.")
        if math.dist(self.head, self.tail) <= 1e-8:
            raise ValueError(f'Bone "{self.name}" has zero length.')


def bounds_from_vertices(vertices: Iterable[Sequence[float]]) -> MeshBounds:
    iterator = iter(vertices)
    try:
        first = tuple(float(v) for v in next(iterator))
    except StopIteration as exc:
        raise ValueError("Cannot fit a rig to an empty mesh.") from exc
    if len(first) != 3:
        raise ValueError("Mesh vertices must have three coordinates.")
    low = list(first)
    high = list(first)
    for vertex in iterator:
        point = tuple(float(v) for v in vertex)
        if len(point) != 3 or any(not math.isfinite(v) for v in point):
            raise ValueError("Mesh vertices must contain three finite coordinates.")
        for axis in range(3):
            low[axis] = min(low[axis], point[axis])
            high[axis] = max(high[axis], point[axis])
    return MeshBounds(tuple(low), tuple(high))


def fit_canonical_biped(bounds: MeshBounds) -> tuple[BoneSpec, ...]:
    """Fit an 18 bone A-pose skeleton to a Z-up mesh envelope."""

    x, y = bounds.center_x, bounds.center_y
    width, depth, height = bounds.width, bounds.depth, bounds.height
    floor = bounds.minimum[2]

    def point(x_offset: float, y_offset: float, z_fraction: float) -> Point3:
        return (x + x_offset * width, y + y_offset * depth, floor + z_fraction * height)

    root = point(0, 0, 0.02)
    pelvis = point(0, 0, 0.50)
    spine = point(0, 0, 0.62)
    chest = point(0, 0, 0.73)
    neck = point(0, 0, 0.84)
    head = point(0, 0, 0.97)
    specs = [
        BoneSpec("root", None, root, pelvis, False),
        BoneSpec("pelvis", "root", pelvis, spine),
        BoneSpec("spine", "pelvis", spine, chest),
        BoneSpec("chest", "spine", chest, neck),
        BoneSpec("neck", "chest", neck, point(0, 0, 0.89)),
        BoneSpec("head", "neck", point(0, 0, 0.89), head),
    ]
    # Front views look from -Y; anatomical left is +X.
    for side, sign in (("L", 1), ("R", -1)):
        shoulder = point(sign * 0.23, 0, 0.73)
        elbow = point(sign * 0.36, 0, 0.61)
        wrist = point(sign * 0.46, 0, 0.49)
        finger = point(sign * 0.49, 0, 0.45)
        hip = point(sign * 0.16, 0, 0.49)
        knee = point(sign * 0.17, 0, 0.27)
        ankle = point(sign * 0.17, 0, 0.07)
        toe = point(sign * 0.17, -0.33, 0.035)
        specs.extend((
            BoneSpec(f"upper_arm.{side}", "chest", shoulder, elbow),
            BoneSpec(f"forearm.{side}", f"upper_arm.{side}", elbow, wrist),
            BoneSpec(f"hand.{side}", f"forearm.{side}", wrist, finger),
            BoneSpec(f"thigh.{side}", "pelvis", hip, knee),
            BoneSpec(f"shin.{side}", f"thigh.{side}", knee, ankle),
            BoneSpec(f"foot.{side}", f"shin.{side}", ankle, toe),
        ))
    return tuple(specs)


def distance_to_bone(point: Sequence[float], bone: BoneSpec) -> float:
    segment = tuple(bone.tail[i] - bone.head[i] for i in range(3))
    offset = tuple(float(point[i]) - bone.head[i] for i in range(3))
    length_squared = sum(component * component for component in segment)
    fraction = max(0.0, min(1.0, sum(a * b for a, b in zip(offset, segment)) / length_squared))
    closest = tuple(bone.head[i] + fraction * segment[i] for i in range(3))
    return math.dist(point, closest)


def fallback_weights(
    point: Sequence[float], bones: Sequence[BoneSpec], *, max_influences: int = 4
) -> dict[str, float]:
    """Finite, normalized skin weights when Blender bone heat cannot bind."""

    if max_influences < 1:
        raise ValueError("max_influences must be positive.")
    deform = [bone for bone in bones if bone.deform]
    if not deform:
        raise ValueError("At least one deforming bone is required.")
    candidates = sorted((distance_to_bone(point, bone), bone.name) for bone in deform)
    closest = candidates[:max_influences]
    if closest[0][0] <= 1e-8:
        return {closest[0][1]: 1.0}
    raw = [(name, 1.0 / max(distance, 1e-6) ** 4) for distance, name in closest]
    total = sum(weight for _, weight in raw)
    return {name: weight / total for name, weight in raw}
