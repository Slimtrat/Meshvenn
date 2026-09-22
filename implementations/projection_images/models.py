from __future__ import annotations

from dataclasses import dataclass, field

from ...core.image_mask import BinaryMask
from ...core.projection_alignment import ProjectionAlignment
from ...core.native_bridge import NativeProjection
from ...core.projected_material import ProjectedMaterialView


@dataclass(frozen=True)
class PreparedProjectionView:
    """One immutable source view shared by geometry and material stages."""

    name: str
    image_name: str
    width: int
    height: int
    azimuth_degrees: float
    elevation_degrees: float
    flip_x: bool
    weight: float
    mask: BinaryMask
    native_projection: NativeProjection
    material_view: ProjectedMaterialView
    alignment: ProjectionAlignment = field(default_factory=ProjectionAlignment)

    @property
    def mask_pixels(self) -> int:
        return self.mask.occupied_count

    @property
    def empty_mask(self) -> bool:
        return self.mask_pixels == 0


@dataclass(frozen=True)
class ProjectionImagesOutput:
    """Output contract of the built-in ``projection-images`` input stage."""

    views: tuple[PreparedProjectionView, ...]
    alpha_threshold: float
    enabled_projection_count: int
    missing_image_count: int

    @property
    def projection_count(self) -> int:
        return len(self.views)

    @property
    def native_projections(self) -> tuple[NativeProjection, ...]:
        return tuple(view.native_projection for view in self.views)

    @property
    def material_views(self) -> tuple[ProjectedMaterialView, ...]:
        return tuple(view.material_view for view in self.views)

    @property
    def view_names(self) -> tuple[str, ...]:
        return tuple(view.name for view in self.views)

    @property
    def empty_mask_count(self) -> int:
        return sum(1 for view in self.views if view.empty_mask)

    @property
    def total_mask_pixels(self) -> int:
        return sum(view.mask_pixels for view in self.views)
