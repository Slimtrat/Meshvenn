"""Sparse continuous silhouette sampling: no production-sized Python volume.

The native mesh stays responsible for connectivity. This field only corrects
vertex positions within the refinement's existing trust region. EDT memory is
linear in source pixels; projection work is linear in surface vertices, not in
the voxel cube. No source GLB geometry or skeleton is consulted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from .geometry_contracts import GeometryProjectionSpace
from .projection_math import project_normalized_point, surface_position_to_normalized
from .sdf.projection import SDFProjection
from .image_mask import BinaryMask
from .projection_math import compile_projection

MAX_VIEW_PIXELS = 4_194_304
MAX_TOTAL_PIXELS = 16_777_216
MAX_VIEWS = 32


def _check_budget(sizes):
    if len(sizes) > MAX_VIEWS or max(sizes, default=0) > MAX_VIEW_PIXELS or sum(sizes) > MAX_TOTAL_PIXELS:
        raise ValueError("Organic contour fitting exceeds its image budget "
                         "(32 views, 4M pixels/view, 16M pixels total). "
                         "Use smaller projections or the Faithful surface finish.")


def sample_mask_gradient(field, u: float, v: float):
    """Bilinear signed distance and exact UV derivatives, including outside UV."""
    if not math.isfinite(u) or not math.isfinite(v):
        raise ValueError("Contour UV coordinates must be finite.")
    cu, cv = min(1., max(0., u)), min(1., max(0., v))
    x, y = cu*(field.width-1), cv*(field.height-1)
    x0, y0 = min(int(x), max(0,field.width-2)), min(int(y), max(0,field.height-2))
    x1, y1 = min(x0+1,field.width-1), min(y0+1,field.height-1)
    tx, ty = x-x0, y-y0
    a,b,c,d = (field.values[y0*field.width+x0], field.values[y0*field.width+x1],
               field.values[y1*field.width+x0], field.values[y1*field.width+x1])
    value = (1-ty)*(a+(b-a)*tx)+ty*(c+(d-c)*tx)
    du = ((1-ty)*(b-a)+ty*(d-c))*(field.width-1)
    dv = ((1-tx)*(c-a)+tx*(d-b))*(field.height-1)
    if cu != u or cv != v:
        dx, dy = (u-cu)*field.domain_width, (v-cv)*field.domain_height
        distance = math.hypot(dx,dy)
        du = (du if cu == u and value > 0 else 0.) + dx/distance*field.domain_width
        dv = (dv if cv == v and value > 0 else 0.) + dy/distance*field.domain_height
        value = max(0.,value)+distance
    return value,du,dv


@dataclass(frozen=True)
class ContourSurface:
    projections: tuple[SDFProjection, ...]
    space: GeometryProjectionSpace

    def __post_init__(self):
        object.__setattr__(self, "projections", tuple(self.projections))
        if len(self.projections) < 2:
            raise ValueError("Contour surface requires at least two silhouettes.")
        if any(not isinstance(p, SDFProjection) for p in self.projections):
            raise TypeError("Contour surface requires signed-distance projections.")
        _check_budget([p.width*p.height for p in self.projections])
        if any(p.empty for p in self.projections):
            raise ValueError("An empty silhouette has no contour surface.")
        if not isinstance(self.space, GeometryProjectionSpace):
            raise TypeError("Contour surface requires a projection-space contract.")

    @classmethod
    def from_views(cls, views: Iterable, space: GeometryProjectionSpace, *, cache: dict | None = None):
        # Validate all inputs and budgets before allocating any EDT buffers.
        if not isinstance(space, GeometryProjectionSpace):
            raise TypeError("Contour surface requires a projection-space contract.")
        views = tuple(views)
        if len(views) < 2:
            raise ValueError("Contour surface requires at least two silhouettes.")
        if any(not isinstance(getattr(view,"mask",None),BinaryMask) for view in views):
            raise TypeError("Contour views must expose BinaryMask silhouettes.")
        _check_budget([view.mask.width*view.mask.height for view in views])
        for view in views:
            if not any(view.mask.values):
                raise ValueError("An empty silhouette has no contour surface.")
            azimuth = float(view.azimuth_degrees)
            elevation = float(view.elevation_degrees)
            if not math.isfinite(azimuth) or not math.isfinite(elevation):
                raise ValueError("Contour projection angles must be finite.")
            compile_projection(azimuth_degrees=azimuth, elevation_degrees=elevation)
        projections = []
        for view in views:
            # Sheet-local cache: immutable masks prevent stale pixel reuse.
            key = (view.mask, float(view.azimuth_degrees), float(view.elevation_degrees),
                   bool(getattr(view,"flip_x",False)), str(getattr(view,"name","Projection")))
            projection = cache.get(key) if cache is not None else None
            if projection is None:
                projection = SDFProjection.from_source_view(view)
                if cache is not None:
                    cache[key] = projection
            projections.append(projection)
        return cls(tuple(projections),space)

    def sample(self, point):
        if len(point) != 3 or any(not math.isfinite(x) for x in point):
            raise ValueError("Contour positions must contain three finite coordinates.")
        normalized = surface_position_to_normalized(point, **self.space.as_projection_kwargs())
        winner, gradient = -math.inf, (0.,0.,0.)
        sx = self.space.width*self.space.voxel_size
        sy = self.space.depth*self.space.voxel_size
        sz = self.space.height*self.space.voxel_size
        for projection in self.projections:
            t = projection.transform
            uv = project_normalized_point(normalized,t)
            value,du,dv = sample_mask_gradient(projection.field,uv.u,uv.v)
            if value <= winner:
                continue
            if t.flip_x:
                du = -du
            hu, hv = t.horizontal_extent, t.vertical_extent
            gradient = (du*t.cos_az/(sx*hu) + dv*t.sin_az*t.sin_el/(sx*hv),
                        -du*t.sin_az/(sy*hu) + dv*t.cos_az*t.sin_el/(sy*hv),
                        dv*t.cos_el/(sz*hv))
            winner = value
        return winner,gradient

    def project(self, point, anchor, limit: float, *, iterations: int = 6):
        """Safeguarded Newton projection on the intersected silhouettes.

        Hard max preserves the visual hull rather than inflating seams. A
        failed or flat-gradient projection keeps its best bounded candidate.
        """
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError("Contour displacement limit must be finite and positive.")
        if not isinstance(iterations,int) or isinstance(iterations,bool) or not 0 <= iterations <= 16:
            raise ValueError("Contour projection iterations must be an integer in 0..16.")
        if any(len(p) != 3 or any(not math.isfinite(x) for x in p) for p in (point,anchor)):
            raise ValueError("Contour positions must contain three finite coordinates.")
        distance = math.dist(point,anchor)
        current = tuple(anchor[k]+(point[k]-anchor[k])*min(1.,limit/distance) for k in range(3)) if distance else tuple(point)
        for _ in range(iterations):
            value,g = self.sample(current)
            norm2 = sum(x*x for x in g)
            if norm2 <= 1e-20 or abs(value)/math.sqrt(norm2) <= limit*.01:
                break
            delta = tuple(-value*x/norm2 for x in g)
            distance = math.sqrt(sum(x*x for x in delta))
            if distance > limit*.5:
                delta = tuple(x*limit*.5/distance for x in delta)
            for attempt in range(6):
                factor = 2.**(-attempt)
                candidate = tuple(current[k]+delta[k]*factor for k in range(3))
                distance = math.dist(candidate,anchor)
                if distance > limit:
                    candidate = tuple(anchor[k]+(candidate[k]-anchor[k])*limit/distance for k in range(3))
                result,_ = self.sample(candidate)
                if abs(result) < abs(value):
                    current = candidate
                    break
            else:
                break
        return current

    def residual(self, points):
        return self.residual_summary(points)["mean_in_voxels"]

    def residual_summary(self, points):
        distances = []
        total = 0
        for point in points:
            total += 1
            value,g = self.sample(point)
            norm = math.sqrt(sum(x*x for x in g))
            if norm > 1e-10:
                distances.append(abs(value)/norm/self.space.voxel_size)
        return {"mean_in_voxels": math.fsum(distances)/len(distances) if distances else None,
                "valid_samples": len(distances), "total_samples": total}
