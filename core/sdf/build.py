from __future__ import annotations

import math
from array import array
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from ..projection_math import NormalizedPoint, grid_to_normalized
from .constants import (
    DEFAULT_ISO_LEVEL,
    DEFAULT_REFERENCE_MAX_VOXELS,
    DEFAULT_SMOOTHNESS,
    DEFAULT_SURFACE_OFFSET,
    DEFAULT_SYMMETRY_X,
    SIGN_EPSILON,
)
from .fusion import sample_fused_sdf
from .projection import SDFProjection, build_sdf_projections
from .utils import require_finite
from .volume import SDFVolume


@dataclass(frozen=True)
class SDFBuildConfig:
    """Configuration for the deterministic pure-Python SDF reference builder."""

    width: int
    depth: int
    height: int
    symmetry_x: bool = DEFAULT_SYMMETRY_X
    smoothness: float = DEFAULT_SMOOTHNESS
    surface_offset: float = DEFAULT_SURFACE_OFFSET
    iso_level: float = DEFAULT_ISO_LEVEL
    max_voxels: int = DEFAULT_REFERENCE_MAX_VOXELS

    def validate(self) -> None:
        for name, value in (
            ("width", self.width),
            ("depth", self.depth),
            ("height", self.height),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 2:
                raise ValueError(f"{name} must be an integer >= 2.")
        if require_finite(self.smoothness, name="smoothness") < 0.0:
            raise ValueError("smoothness cannot be negative.")
        require_finite(self.surface_offset, name="surface_offset")
        require_finite(self.iso_level, name="iso_level")
        if (
            not isinstance(self.max_voxels, int)
            or isinstance(self.max_voxels, bool)
            or self.max_voxels <= 0
        ):
            raise ValueError("max_voxels must be a positive integer.")
        if self.voxel_count > self.max_voxels:
            raise ValueError(
                "Requested pure-Python SDF volume is too large: "
                f"{self.voxel_count} samples, limit {self.max_voxels}. "
                "Use the future native SDF backend for production-sized fields."
            )

    @property
    def voxel_count(self) -> int:
        return self.width * self.depth * self.height

    @property
    def dimensions(self) -> tuple[int, int, int]:
        return self.width, self.depth, self.height


def cubic_sdf_config(
    resolution: int,
    *,
    symmetry_x: bool = DEFAULT_SYMMETRY_X,
    smoothness: float = DEFAULT_SMOOTHNESS,
    surface_offset: float = DEFAULT_SURFACE_OFFSET,
    iso_level: float = DEFAULT_ISO_LEVEL,
    max_voxels: int = DEFAULT_REFERENCE_MAX_VOXELS,
) -> SDFBuildConfig:
    config = SDFBuildConfig(
        width=int(resolution),
        depth=int(resolution),
        height=int(resolution),
        symmetry_x=bool(symmetry_x),
        smoothness=float(smoothness),
        surface_offset=float(surface_offset),
        iso_level=float(iso_level),
        max_voxels=int(max_voxels),
    )
    config.validate()
    return config


@dataclass(frozen=True)
class SDFBuildProgress:
    completed_slices: int
    total_slices: int

    @property
    def fraction(self) -> float:
        if self.total_slices <= 0:
            return 1.0
        return float(self.completed_slices) / float(self.total_slices)


@dataclass(frozen=True)
class SDFBuildStats:
    projection_count: int
    voxel_count: int
    projection_sample_count: int
    negative_samples: int
    zero_samples: int
    positive_samples: int
    minimum_distance: float
    maximum_distance: float
    symmetry_x: bool
    smoothness: float
    surface_offset: float
    iso_level: float

    @property
    def inside_samples(self) -> int:
        return self.negative_samples + self.zero_samples

    @property
    def outside_samples(self) -> int:
        return self.positive_samples

    @property
    def inside_ratio(self) -> float:
        if self.voxel_count <= 0:
            return 0.0
        return float(self.inside_samples) / float(self.voxel_count)


@dataclass(frozen=True)
class SDFBuildResult:
    volume: SDFVolume
    stats: SDFBuildStats
    projections: tuple[SDFProjection, ...]
    config: SDFBuildConfig


def build_sdf_volume(
    projections: Sequence[SDFProjection],
    *,
    config: SDFBuildConfig,
    progress_callback: Callable[[SDFBuildProgress], None] | None = None,
) -> SDFBuildResult:
    """Build the deterministic pure-Python reference field."""
    if not isinstance(config, SDFBuildConfig):
        raise TypeError("config must be SDFBuildConfig.")
    config.validate()
    resolved_projections = tuple(projections)
    if not resolved_projections:
        raise ValueError("At least one SDF projection is required.")
    if any(not isinstance(projection, SDFProjection) for projection in resolved_projections):
        raise TypeError("All projections must be SDFProjection instances.")
    if progress_callback is not None and not callable(progress_callback):
        raise TypeError("progress_callback must be callable.")

    width, depth, height = config.dimensions
    voxel_count = config.voxel_count
    values = array("f", [0.0]) * voxel_count
    normalized_x = tuple(grid_to_normalized(index, width) for index in range(width))
    normalized_y = tuple(grid_to_normalized(index, depth) for index in range(depth))
    normalized_z = tuple(grid_to_normalized(index, height) for index in range(height))
    negative_samples = zero_samples = positive_samples = 0
    minimum_distance, maximum_distance = math.inf, -math.inf
    target_index = 0

    for z_index, nz in enumerate(normalized_z):
        for ny in normalized_y:
            for nx in normalized_x:
                value = sample_fused_sdf(
                    NormalizedPoint(x=nx, y=ny, z=nz),
                    resolved_projections,
                    symmetry_x=config.symmetry_x,
                    smoothness=config.smoothness,
                    surface_offset=config.surface_offset,
                )
                values[target_index] = float(value)
                target_index += 1
                minimum_distance = min(minimum_distance, value)
                maximum_distance = max(maximum_distance, value)
                relative = value - config.iso_level
                if relative < -SIGN_EPSILON:
                    negative_samples += 1
                elif relative > SIGN_EPSILON:
                    positive_samples += 1
                else:
                    zero_samples += 1
        if progress_callback is not None:
            progress_callback(SDFBuildProgress(completed_slices=z_index + 1, total_slices=height))

    projection_sample_count = voxel_count * len(resolved_projections) * (2 if config.symmetry_x else 1)
    volume = SDFVolume(
        width=width, depth=depth, height=height, values=values, iso_level=config.iso_level
    )
    stats = SDFBuildStats(
        projection_count=len(resolved_projections),
        voxel_count=voxel_count,
        projection_sample_count=projection_sample_count,
        negative_samples=negative_samples,
        zero_samples=zero_samples,
        positive_samples=positive_samples,
        minimum_distance=float(minimum_distance),
        maximum_distance=float(maximum_distance),
        symmetry_x=config.symmetry_x,
        smoothness=config.smoothness,
        surface_offset=config.surface_offset,
        iso_level=config.iso_level,
    )
    return SDFBuildResult(
        volume=volume, stats=stats, projections=resolved_projections, config=config
    )


def build_sdf_from_views(
    views: Iterable[Any],
    *,
    config: SDFBuildConfig,
    progress_callback: Callable[[SDFBuildProgress], None] | None = None,
) -> SDFBuildResult:
    return build_sdf_volume(
        build_sdf_projections(views),
        config=config,
        progress_callback=progress_callback,
    )
