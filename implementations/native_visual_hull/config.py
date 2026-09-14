from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ...core.geometry_contracts import GeometryProjectionSpace
from ...core.native_bridge import NativeVolume, normalize_mesh_mode
from ...core.pipeline_contracts import PipelineContext
from .constants import DEFAULT_CENTER_XY, DEFAULT_MESH_MODE, DEFAULT_VOXEL_SIZE


def _resolve_settings(context: PipelineContext) -> Any:
    if context.settings is not None:
        return context.settings
    scene = context.scene
    if scene is None:
        return None
    return getattr(scene, "bpt_settings", None)


@dataclass(frozen=True)
class NativeVisualHullConfig:
    resolution: int
    symmetry_x: bool
    thread_count: int
    mesh_mode: str
    voxel_size: float
    center_xy: bool
    normalize_height: bool
    target_height: float

    def validate(self) -> None:
        if self.resolution < 16 or self.resolution > 256:
            raise ValueError("Resolution must be between 16 and 256.")
        if self.thread_count < 0:
            raise ValueError("Thread count cannot be negative.")
        if not math.isfinite(self.voxel_size) or self.voxel_size <= 0.0:
            raise ValueError("Voxel size must be finite and greater than zero.")
        if not math.isfinite(self.target_height) or self.target_height <= 0.0:
            raise ValueError("Target height must be finite and greater than zero.")
        normalize_mesh_mode(self.mesh_mode)


def _config_from_settings(settings: Any) -> NativeVisualHullConfig:
    """
    Resolve implementation configuration from current
    Blender settings.

    mesh_mode and voxel_size are read defensively so this
    adapter already supports future implementation-specific
    PropertyGroups without breaking the current settings
    model.
    """
    mesh_mode = str(getattr(settings, "mesh_mode", DEFAULT_MESH_MODE))
    voxel_size = float(getattr(settings, "voxel_size", DEFAULT_VOXEL_SIZE))
    config = NativeVisualHullConfig(
        resolution=int(settings.resolution),
        symmetry_x=bool(settings.symmetry_x),
        thread_count=int(settings.thread_count),
        mesh_mode=mesh_mode,
        voxel_size=voxel_size,
        center_xy=DEFAULT_CENTER_XY,
        normalize_height=bool(settings.normalize_height),
        target_height=float(settings.target_height),
    )
    config.validate()
    return config


def _projection_space_from_volume(
    volume: NativeVolume, config: NativeVisualHullConfig
) -> GeometryProjectionSpace:
    """
    Adapt NativeVolume into the algorithm-neutral coordinate
    contract consumed by downstream stages.
    """
    return GeometryProjectionSpace(
        width=int(volume.width),
        depth=int(volume.depth),
        height=int(volume.height),
        voxel_size=float(config.voxel_size),
        center_xy=bool(config.center_xy),
    )
