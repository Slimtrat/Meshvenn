from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from ..image_mask import BinaryMask
from ..projection_math import (
    NormalizedPoint,
    ProjectionTransform,
    compile_projection,
    project_normalized_point,
)
from .mask import SignedDistanceMask, build_signed_distance_mask


@dataclass(frozen=True)
class SDFProjection:
    """One silhouette constraint converted to continuous signed distance."""

    name: str
    transform: ProjectionTransform
    field: SignedDistanceMask

    def __post_init__(self) -> None:
        name = str(self.name).strip() or "Projection"
        object.__setattr__(self, "name", name)
        if not isinstance(self.transform, ProjectionTransform):
            raise TypeError("transform must be ProjectionTransform.")
        if not isinstance(self.field, SignedDistanceMask):
            raise TypeError("field must be SignedDistanceMask.")
        if not math.isclose(
            self.field.horizontal_extent,
            self.transform.horizontal_extent,
            rel_tol=1e-7,
            abs_tol=1e-7,
        ):
            raise ValueError("Signed-distance horizontal extent does not match projection transform.")
        if not math.isclose(
            self.field.vertical_extent,
            self.transform.vertical_extent,
            rel_tol=1e-7,
            abs_tol=1e-7,
        ):
            raise ValueError("Signed-distance vertical extent does not match projection transform.")

    @property
    def width(self) -> int:
        return self.field.width

    @property
    def height(self) -> int:
        return self.field.height

    @property
    def empty(self) -> bool:
        return self.field.empty

    def sample(self, point: NormalizedPoint) -> float:
        projected = project_normalized_point(point, self.transform)
        return self.field.sample_uv(projected.u, projected.v)

    @classmethod
    def from_mask(
        cls,
        mask: BinaryMask,
        *,
        azimuth_degrees: float,
        elevation_degrees: float,
        flip_x: bool = False,
        name: str = "Projection",
    ) -> "SDFProjection":
        transform = compile_projection(
            azimuth_degrees=azimuth_degrees,
            elevation_degrees=elevation_degrees,
            flip_x=flip_x,
        )
        field = build_signed_distance_mask(
            mask,
            horizontal_extent=transform.horizontal_extent,
            vertical_extent=transform.vertical_extent,
        )
        return cls(name=name, transform=transform, field=field)

    @classmethod
    def from_source_view(cls, view: Any) -> "SDFProjection":
        mask = getattr(view, "mask", None)
        if not isinstance(mask, BinaryMask):
            raise TypeError("Source view does not expose a BinaryMask.")
        return cls.from_mask(
            mask,
            azimuth_degrees=float(getattr(view, "azimuth_degrees")),
            elevation_degrees=float(getattr(view, "elevation_degrees")),
            flip_x=bool(getattr(view, "flip_x", False)),
            name=str(getattr(view, "name", "Projection")),
        )


def build_sdf_projections(views: Iterable[Any]) -> tuple[SDFProjection, ...]:
    result = tuple(SDFProjection.from_source_view(view) for view in views)
    if not result:
        raise ValueError("At least one projection is required.")
    return result
