"""Visibility-aware correspondences on original-image grids, without verdicts.

All rays use the native projector's null-space direction. The legacy material
direction helper remains unchanged; positive native elevation views from -Z.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from ..diagnostic_contracts import ViewRevision
from ..material_visibility import MeshVisibilityTester, RaycastHit
from ..projection_math.models import NormalizedPoint
from ..projection_math.projection import (project_normalized_point, projection_aligned_axes,
                                         unproject_normalized_uv)
from .bvh import TriangleBVH, WorkBudget, dot
from .surface import SurfaceMesh

MAX_RASTER_SIDE = 128
MAX_REFERENCES = 8


@dataclass(frozen=True)
class ReferenceCorrespondence:
    view_id: str
    projected_uv: tuple[float, float] | None
    original_uv: tuple[float, float] | None
    state: str
    visible: bool
    grazing: bool
    facing: float | None
    reason: str
    occluder_triangle: int | None = None
    occluded: bool = False
    backfacing: bool = False


@dataclass(frozen=True)
class PixelCorrespondence:
    x: int
    y: int
    target_uv: tuple[float, float]
    target_original_uv: tuple[float, float]
    point3d: tuple[float, float, float] | None
    normal3d: tuple[float, float, float] | None
    triangle_index: int | None
    state: str
    reason: str
    references: tuple[ReferenceCorrespondence, ...] = ()
    facing: float | None = None


@dataclass(frozen=True)
class CorrespondenceMap:
    width: int
    height: int
    target_view_id: str
    reference_view_ids: tuple[str, ...]
    pixels: tuple[PixelCorrespondence, ...]
    mesh_sha256: str
    work_units: int
    surface_epsilon: float
    ray_convention: str = "native-projector-null-space-v1"


class SurfaceSampler:
    """Reusable bounded BVH and shared work/deadline budget across image maps.

    Source triangle winding is authoritative, never corrected. Unsupported or
    unverified cameras remain unknown. A clear ray only describes this declared
    mesh; it does not prove the object's physical shape or semantic identity.
    """
    def __init__(self, mesh: SurfaceMesh, *, deadline=None, cancel=None,
                 max_work=4_000_000, min_facing=.1, surface_epsilon=1e-6):
        if type(mesh) is not SurfaceMesh:
            raise TypeError("SurfaceSampler requires a typed immutable SurfaceMesh.")
        if (type(min_facing) not in (int, float) or not math.isfinite(min_facing) or not 0 < min_facing <= 1
                or type(surface_epsilon) not in (int, float) or not math.isfinite(surface_epsilon)
                or not 0 < surface_epsilon <= 1e-3):
            raise ValueError("Facing threshold and surface epsilon must be finite in their supported bounds.")
        self.mesh, self.min_facing, self.surface_epsilon = mesh, min_facing, surface_epsilon
        self.budget = WorkBudget(max_work, deadline, cancel)
        self.bvh = TriangleBVH(mesh, self.budget)
        self._last_visibility_hit = None
        self.visibility = MeshVisibilityTester(self._raycast, surface_epsilon=surface_epsilon, max_distance=8.)

    @property
    def work_units(self):
        return self.budget.used

    def _raycast(self, origin, direction, distance):
        hit = self.bvh.cast(origin, direction, distance)
        self._last_visibility_hit = hit
        return None if hit is None else RaycastHit(hit.distance, hit.triangle_index, hit.position, hit.normal)

    @staticmethod
    def _camera(view):
        if not view.camera.verified:
            return None
        try:
            transform = view.camera.transform
            return transform, projection_aligned_axes(transform)[2]
        except ValueError:
            return None

    def _facing(self, normal, direction):
        facing = max(-1., min(1., dot(normal, direction)))
        # Roundoff around a perpendicular face is grazing, not a winding repair.
        backfacing = facing < -1e-12
        return facing, backfacing, not backfacing and facing <= self.min_facing

    def _reference(self, point, normal, view, camera):
        if camera is None:
            return ReferenceCorrespondence(view.view_id, None, None, "camera_unknown", False, False,
                None, "No supported independently verified orthographic camera is declared.")
        transform, direction = camera
        projected = project_normalized_point(NormalizedPoint(*point), transform)
        original = view.alignment.source_uv(projected.u, projected.v)
        facing, backfacing, grazing = self._facing(normal, direction)
        if not projected.inside or not all(0 <= value <= 1 for value in original):
            return ReferenceCorrespondence(view.view_id, (projected.u, projected.v), original,
                "outside", False, grazing, facing, "Projected surface point lies outside the original reference image.",
                backfacing=backfacing)
        result = self.visibility.query(point, direction)
        last = self._last_visibility_hit
        if result.occluded:
            return ReferenceCorrespondence(view.view_id, (projected.u, projected.v), original,
                "occluded", False, grazing, facing, "Another declared surface triangle blocks this reference ray.",
                result.polygon_index, True, backfacing)
        if last is not None and (last.ambiguous or last.distance <= self.surface_epsilon):
            return ReferenceCorrespondence(view.view_id, (projected.u, projected.v), original,
                "numerical_unknown", False, grazing, facing, "A near-surface or ambiguous hit is inside the visibility offset tolerance.",
                last.triangle_index, False, backfacing)
        state = "backfacing" if backfacing else "grazing" if grazing else "visible"
        reason = ("Source winding faces away from this reference camera." if backfacing else
                  "Reference ray is too grazing for a supported appearance comparison." if grazing else
                  "The declared surface point is front-facing and unoccluded in this reference.")
        return ReferenceCorrespondence(view.view_id, (projected.u, projected.v), original,
                                       state, state == "visible", grazing, facing, reason, backfacing=backfacing)

    def map_views(self, target: ViewRevision, references: Sequence[ViewRevision], *, width: int,
                  height: int) -> CorrespondenceMap:
        if (any(type(size) is not int or not 1 <= size <= MAX_RASTER_SIDE for size in (width, height))
                or len(references) > MAX_REFERENCES or type(target) is not ViewRevision
                or any(type(view) is not ViewRevision for view in references)):
            raise ValueError("Correspondence maps require bounded dimensions and typed view declarations.")
        references = tuple(references)
        ids = tuple(view.view_id for view in references)
        if len(set(ids)) != len(ids) or target.view_id in ids:
            raise ValueError("Reference view IDs must be unique and differ from the target ID.")
        self.budget.check()
        target_camera = self._camera(target)
        reference_cameras = tuple(self._camera(view) for view in references)
        pixels = []
        for y in range(height):
            self.budget.check()
            for x in range(width):
                self.budget.spend(1 + len(references))
                original = (x/(width-1) if width > 1 else .5, y/(height-1) if height > 1 else .5)
                uv = target.alignment.aligned_uv(*original)
                point = normal = triangle = facing = None
                refs = ()
                if target_camera is None:
                    state, reason = "camera_unknown", "No supported independently verified target camera is declared."
                elif not all(0 <= value <= 1 for value in uv):
                    state, reason = "outside", "Original target sample maps outside the aligned projection frame."
                else:
                    transform, direction = target_camera
                    origin = unproject_normalized_uv(*uv, transform, depth=4.)
                    hit = self.bvh.cast((origin.x, origin.y, origin.z), tuple(-v for v in direction), 8.)
                    if hit is None:
                        state, reason = "no_hit", "The target ray has no intersection with the declared surface."
                    elif hit.ambiguous:
                        point = hit.position
                        state, reason = "ambiguous", "Multiple overlapping or inconsistent surface hits share the target depth."
                    else:
                        point, normal, triangle = hit.position, hit.normal, hit.triangle_index
                        facing, backfacing, grazing = self._facing(normal, direction)
                        state = "backfacing" if backfacing else "grazing" if grazing else "visible"
                        reason = ("Source triangle winding faces away from the target camera." if backfacing else
                            "Target incidence is too grazing for a supported appearance comparison." if grazing else
                            "Nearest declared target surface is front-facing at this original-image sample.")
                        if state == "visible":
                            refs = tuple(self._reference(point, normal, view, camera)
                                         for view, camera in zip(references, reference_cameras))
                pixels.append(PixelCorrespondence(x, y, uv, original, point, normal, triangle,
                                                  state, reason, refs, facing))
        self.budget.check()
        return CorrespondenceMap(width, height, target.view_id, ids, tuple(pixels), self.mesh.sha256,
                                  self.budget.used, self.surface_epsilon)
