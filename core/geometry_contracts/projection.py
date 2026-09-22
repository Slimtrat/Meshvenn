from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any


class GeometryProjectionConvention(str, Enum):
    """
    Coordinate convention used by a GEOMETRY output when
    downstream stages need to project surface positions back
    into the source images.

    SURFACE_ENVELOPE_V1 matches Meshvenn's current native
    projection convention:

        X
            0 .. width * voxel_size

            or, when center_xy=True:

            -width * voxel_size / 2
            ..
            +width * voxel_size / 2

        Y
            same convention using depth

        Z
            0 .. height * voxel_size

    Projection normalization maps the complete surface
    envelope to:

        [-1, +1]

    rather than interpreting surface vertices as voxel
    centres.

    This is the convention already used by
    core/projection_math.py.
    """

    SURFACE_ENVELOPE_V1 = "surface-envelope-v1"


DEFAULT_PROJECTION_CONVENTION = GeometryProjectionConvention.SURFACE_ENVELOPE_V1


@dataclass(frozen=True)
class GeometryProjectionSpace:
    """
    Reconstruction coordinate system shared between
    GEOMETRY and projection-dependent downstream stages.

    This deliberately contains no Blender-specific or
    algorithm-specific state.

    A MATERIAL implementation should need this:

        projection_space.width
        projection_space.depth
        projection_space.height
        projection_space.voxel_size
        projection_space.center_xy

    and should NOT need:

        NativeVolume
        NativeMesh
        SDFVolume
        VisualHullOutput
        implementation internals

    The mesh-local surface coordinates exposed by the
    GeometrySurfaceOutput MUST remain expressed in this
    projection space until every projection-dependent stage
    has completed.
    """

    width: int
    depth: int
    height: int
    voxel_size: float = 1.0
    center_xy: bool = True
    convention: GeometryProjectionConvention = DEFAULT_PROJECTION_CONVENTION

    def __post_init__(self) -> None:
        for name, value in (
            ("width", self.width),
            ("depth", self.depth),
            ("height", self.height),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        voxel_size = float(self.voxel_size)
        if not math.isfinite(voxel_size) or voxel_size <= 0.0:
            raise ValueError("voxel_size must be finite and greater than zero.")
        object.__setattr__(self, "voxel_size", voxel_size)
        object.__setattr__(self, "center_xy", bool(self.center_xy))
        object.__setattr__(
            self, "convention", GeometryProjectionConvention(self.convention)
        )

    @property
    def dimensions(self) -> tuple[int, int, int]:
        return (self.width, self.depth, self.height)

    @property
    def voxel_count(self) -> int:
        return self.width * self.depth * self.height

    @property
    def physical_width(self) -> float:
        return float(self.width) * self.voxel_size

    @property
    def physical_depth(self) -> float:
        return float(self.depth) * self.voxel_size

    @property
    def physical_height(self) -> float:
        return float(self.height) * self.voxel_size

    @property
    def physical_dimensions(self) -> tuple[float, float, float]:
        return (self.physical_width, self.physical_depth, self.physical_height)

    @property
    def minimum_local_point(self) -> tuple[float, float, float]:
        if self.center_xy:
            return (-self.physical_width * 0.5, -self.physical_depth * 0.5, 0.0)
        return (0.0, 0.0, 0.0)

    @property
    def maximum_local_point(self) -> tuple[float, float, float]:
        if self.center_xy:
            return (
                self.physical_width * 0.5,
                self.physical_depth * 0.5,
                self.physical_height,
            )
        return (self.physical_width, self.physical_depth, self.physical_height)

    @property
    def local_bounds(
        self,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        return (self.minimum_local_point, self.maximum_local_point)

    def as_projection_kwargs(self) -> dict[str, Any]:
        """
        Arguments currently consumed by Meshvenn's
        projection functions.

        Typical downstream usage:

            blend_projected_color(
                position,
                normal,
                views,
                **geometry.projection_space
                    .as_projection_kwargs(),
                ...
            )

        This keeps MATERIAL independent from the concrete
        GEOMETRY implementation.
        """
        if self.convention != GeometryProjectionConvention.SURFACE_ENVELOPE_V1:
            raise ValueError(
                f"Projection convention is not supported by the current Meshvenn projection engine: {self.convention.value}"
            )
        return {
            "width": self.width,
            "depth": self.depth,
            "height": self.height,
            "voxel_size": self.voxel_size,
            "center_xy": self.center_xy,
        }
