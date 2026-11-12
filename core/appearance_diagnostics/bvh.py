"""Bounded, two-sided triangle BVH ray tracing for declared surfaces."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from .surface import SurfaceMesh


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


class WorkBudget:
    def __init__(self, max_work, deadline=None, cancel=None):
        if type(max_work) is not int or not 1 <= max_work <= 50_000_000:
            raise ValueError("Surface work budget must be an integer in [1,50000000].")
        if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
            raise ValueError("Surface deadline must be finite.")
        self.limit, self.used, self.deadline, self.cancel = max_work, 0, deadline, cancel
        self.check()

    def check(self):
        if self.cancel is not None and self.cancel():
            raise InterruptedError("Surface correspondence was cancelled.")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError("Surface correspondence deadline exceeded.")

    def spend(self, units=1):
        previous = self.used
        self.used += units
        if self.used > self.limit:
            raise ValueError("Surface correspondence work budget exceeded.")
        if previous // 256 != self.used // 256:
            self.check()


@dataclass(frozen=True)
class Intersection:
    distance: float
    triangle_index: int
    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    barycentric: tuple[float, float, float]
    ambiguous: bool = False


@dataclass(frozen=True)
class _Triangle:
    index: int
    a: tuple
    e: tuple
    f: tuple
    normal: tuple
    area_twice: float
    bounds: tuple
    centroid: tuple
    points: tuple


@dataclass(frozen=True)
class _Node:
    bounds: tuple
    indices: tuple[int, ...] = ()
    left: _Node | None = None
    right: _Node | None = None


class TriangleBVH:
    def __init__(self, mesh: SurfaceMesh, budget: WorkBudget):
        self.budget = budget
        triangles = []
        for index, indices in enumerate(mesh.triangles):
            budget.spend(8)
            a, b, c = (mesh.vertices[i] for i in indices)
            e, f = subtract(b, a), subtract(c, a)
            n = cross(e, f)
            length = math.hypot(*n)
            bounds = tuple(value for axis in range(3) for value in
                           (min(a[axis], b[axis], c[axis]), max(a[axis], b[axis], c[axis])))
            triangles.append(_Triangle(index, a, e, f, tuple(x/length for x in n), length, bounds,
                tuple((a[i]+b[i]+c[i])/3 for i in range(3)), tuple(sorted((a, b, c)))))
        self.triangles = tuple(triangles)
        self.root = self._build(tuple(range(len(triangles))))
        budget.check()

    def _build(self, indices):
        self.budget.spend(len(indices) * (2 + math.ceil(math.log2(max(1, len(indices))))))
        bounds = tuple(value for axis in range(3) for value in
            (min(self.triangles[i].bounds[2*axis] for i in indices),
             max(self.triangles[i].bounds[2*axis+1] for i in indices)))
        if len(indices) <= 8:
            return _Node(bounds, indices)
        axis = max(range(3), key=lambda axis: bounds[axis*2+1]-bounds[axis*2])
        ordered = sorted(indices, key=lambda i: (self.triangles[i].centroid[axis], i))
        middle = len(ordered)//2
        return _Node(bounds, left=self._build(tuple(ordered[:middle])), right=self._build(tuple(ordered[middle:])))

    @staticmethod
    def _box(bounds, origin, direction, maximum):
        near, far = 0.0, maximum
        for axis in range(3):
            if abs(direction[axis]) < 1e-15:
                if not bounds[axis*2]-1e-12 <= origin[axis] <= bounds[axis*2+1]+1e-12:
                    return None
                continue
            a = (bounds[axis*2]-origin[axis])/direction[axis]
            b = (bounds[axis*2+1]-origin[axis])/direction[axis]
            near, far = max(near, min(a, b)), min(far, max(a, b))
            if near > far + 1e-12:
                return None
        return near

    @staticmethod
    def _triangle(triangle, origin, direction, maximum):
        p = cross(direction, triangle.f)
        determinant = dot(triangle.e, p)
        if abs(determinant) <= 1e-12 * triangle.area_twice:
            return None
        inverse = 1 / determinant
        delta = subtract(origin, triangle.a)
        u = dot(delta, p) * inverse
        q = cross(delta, triangle.e)
        v = dot(direction, q) * inverse
        distance = dot(triangle.f, q) * inverse
        if u < -1e-10 or v < -1e-10 or u+v > 1+1e-10 or not 0 <= distance <= maximum:
            return None
        return Intersection(distance, triangle.index,
            tuple(origin[i]+distance*direction[i] for i in range(3)), triangle.normal, (1-u-v, u, v))

    def cast(self, origin, direction, maximum=8.0):
        if (not all(math.isfinite(x) for x in (*origin, *direction, maximum)) or maximum <= 0
                or not math.isclose(math.hypot(*direction), 1.0, abs_tol=1e-10)):
            raise ValueError("A BVH ray requires finite position, unit direction and positive length.")
        best, tie = None, 1e-8
        pending = [self.root]
        while pending:
            node = pending.pop()
            self.budget.spend()
            maximum_now = min(maximum, best.distance+tie) if best else maximum
            if self._box(node.bounds, origin, direction, maximum_now) is None:
                continue
            if node.indices:
                for index in node.indices:
                    self.budget.spend(4)
                    hit = self._triangle(self.triangles[index], origin, direction, maximum_now)
                    if hit is None:
                        continue
                    if best is None or hit.distance < best.distance-tie:
                        best = hit
                    elif abs(hit.distance-best.distance) <= tie:
                        same_geometry = self.triangles[index].points == self.triangles[best.triangle_index].points
                        ambiguous = (best.ambiguous or same_geometry or min(hit.barycentric) > 1e-8
                            or min(best.barycentric) > 1e-8 or dot(hit.normal, best.normal) < 1-1e-8)
                        chosen = hit if hit.triangle_index < best.triangle_index else best
                        best = Intersection(chosen.distance, chosen.triangle_index, chosen.position,
                            chosen.normal, chosen.barycentric, ambiguous)
            else:
                children = [(self._box(child.bounds, origin, direction, maximum_now), child)
                            for child in (node.left, node.right)]
                pending.extend(child for distance, child in sorted(
                    ((distance, child) for distance, child in children if distance is not None),
                    key=lambda pair: pair[0], reverse=True))
        return best
