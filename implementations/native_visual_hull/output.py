from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping
import bpy

from ...core.geometry_contracts import GeometryProjectionSpace, GeometrySurfaceOutput
from ...core.native_bridge import NativeMesh, NativeVolume, normalize_mesh_mode
from ...core.pipeline_contracts import PipelineContext, PipelineStage
from ..projection_images import ProjectionImagesOutput
from .constants import IMPLEMENTATION_ID


@dataclass(frozen=True, init=False)
class NativeVisualHullOutput(GeometrySurfaceOutput):
    """
    Native Visual Hull specialization of the generic
    GeometrySurfaceOutput contract.

    Generic downstream stages should depend on:

        GeometrySurfaceOutput
            blender_object
            source
            projection_space
            implementation_id
            metrics
            metadata

    Native-specific tooling may additionally use:

        volume
        native_mesh
        resolution
        symmetry_x
        thread_count
        mesh_mode
        normalized_height
        target_height
        normalization_scale

    -------------------------------------------------------
    Coordinate invariant
    -------------------------------------------------------

    The Blender mesh remains in reconstruction-local
    coordinates.

    Object-level scaling is allowed.

    Applying the scale to obj.data before projection-based
    MATERIAL stages is NOT allowed, because that would break:

        surface position
            ↓
        GeometryProjectionSpace
            ↓
        source image projection

    -------------------------------------------------------
    Temporary constructor compatibility
    -------------------------------------------------------

    Existing diagnostic scripts historically instantiate:

        NativeVisualHullOutput(
            ...
            voxel_size=1.0,
            center_xy=True,
        )

    Therefore voxel_size and center_xy remain accepted by
    __init__ while migration is in progress.

    They are no longer stored independently.

    The source of truth is:

        output.projection_space.voxel_size
        output.projection_space.center_xy

    Once all callers use GeometryProjectionSpace directly,
    these compatibility arguments may be removed.
    """

    volume: NativeVolume
    native_mesh: NativeMesh
    resolution: int
    symmetry_x: bool
    thread_count: int
    mesh_mode: str
    normalized_height: bool
    target_height: float | None
    normalization_scale: float

    def __init__(
        self,
        *,
        blender_object: bpy.types.Object,
        volume: NativeVolume,
        native_mesh: NativeMesh,
        source: ProjectionImagesOutput,
        resolution: int,
        symmetry_x: bool,
        thread_count: int,
        mesh_mode: str,
        normalized_height: bool,
        target_height: float | None,
        normalization_scale: float,
        projection_space: GeometryProjectionSpace | None = None,
        voxel_size: float | None = None,
        center_xy: bool | None = None,
        metrics: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if volume is None:
            raise ValueError("NativeVisualHullOutput requires a NativeVolume.")
        if native_mesh is None:
            raise ValueError("NativeVisualHullOutput requires a NativeMesh.")
        normalized_resolution = int(resolution)
        if normalized_resolution < 16 or normalized_resolution > 256:
            raise ValueError("Resolution must be between 16 and 256.")
        normalized_thread_count = int(thread_count)
        if normalized_thread_count < 0:
            raise ValueError("Thread count cannot be negative.")
        normalized_mesh_mode = normalize_mesh_mode(str(mesh_mode))
        normalized_scale = float(normalization_scale)
        if not math.isfinite(normalized_scale) or normalized_scale <= 0.0:
            raise ValueError(
                "normalization_scale must be finite and greater than zero."
            )
        normalized_height_flag = bool(normalized_height)
        normalized_target_height = None
        if target_height is not None:
            normalized_target_height = float(target_height)
            if (
                not math.isfinite(normalized_target_height)
                or normalized_target_height <= 0.0
            ):
                raise ValueError("target_height must be finite and greater than zero.")
        if normalized_height_flag and normalized_target_height is None:
            raise ValueError(
                "target_height is required when normalized_height is enabled."
            )
        volume_width = int(volume.width)
        volume_depth = int(volume.depth)
        volume_height = int(volume.height)
        if projection_space is None:
            resolved_voxel_size = (
                DEFAULT_VOXEL_SIZE if voxel_size is None else float(voxel_size)
            )
            resolved_center_xy = (
                DEFAULT_CENTER_XY if center_xy is None else bool(center_xy)
            )
            projection_space = GeometryProjectionSpace(
                width=volume_width,
                depth=volume_depth,
                height=volume_height,
                voxel_size=resolved_voxel_size,
                center_xy=resolved_center_xy,
            )
        else:
            if not isinstance(projection_space, GeometryProjectionSpace):
                raise TypeError("projection_space must be a GeometryProjectionSpace.")
            expected_dimensions = (volume_width, volume_depth, volume_height)
            if projection_space.dimensions != expected_dimensions:
                raise ValueError(
                    f"Projection-space dimensions do not match NativeVolume.\nProjection space: {projection_space.dimensions}\nNative volume:    {expected_dimensions}"
                )
            if voxel_size is not None:
                legacy_voxel_size = float(voxel_size)
                if not math.isclose(
                    legacy_voxel_size,
                    projection_space.voxel_size,
                    rel_tol=1e-09,
                    abs_tol=1e-09,
                ):
                    raise ValueError(
                        "Legacy voxel_size does not match projection_space."
                    )
            if center_xy is not None and bool(center_xy) != projection_space.center_xy:
                raise ValueError("Legacy center_xy does not match projection_space.")
        resolved_metrics = dict(metrics or {})
        resolved_metrics.setdefault("projection_count", int(source.projection_count))
        resolved_metrics.setdefault("resolution", normalized_resolution)
        resolved_metrics.setdefault("occupied_voxels", int(volume.occupied_count))
        resolved_metrics.setdefault("vertex_count", int(native_mesh.vertex_count))
        resolved_metrics.setdefault("index_count", int(native_mesh.index_count))
        resolved_metrics.setdefault("polygon_count", int(native_mesh.polygon_count))
        resolved_metrics.setdefault("normalization_scale", normalized_scale)
        resolved_metadata = dict(metadata or {})
        resolved_metadata.setdefault("mesh_mode", normalized_mesh_mode)
        resolved_metadata.setdefault("symmetry_x", bool(symmetry_x))
        resolved_metadata.setdefault("thread_count", normalized_thread_count)
        resolved_metadata.setdefault("normalized_height", normalized_height_flag)
        resolved_metadata.setdefault("target_height", normalized_target_height)
        GeometrySurfaceOutput.__init__(
            self,
            blender_object=blender_object,
            source=source,
            projection_space=projection_space,
            implementation_id=IMPLEMENTATION_ID,
            metrics=resolved_metrics,
            metadata=resolved_metadata,
        )
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "native_mesh", native_mesh)
        object.__setattr__(self, "resolution", normalized_resolution)
        object.__setattr__(self, "symmetry_x", bool(symmetry_x))
        object.__setattr__(self, "thread_count", normalized_thread_count)
        object.__setattr__(self, "mesh_mode", normalized_mesh_mode)
        object.__setattr__(self, "normalized_height", normalized_height_flag)
        object.__setattr__(self, "target_height", normalized_target_height)
        object.__setattr__(self, "normalization_scale", normalized_scale)

    @property
    def projection_count(self) -> int:
        return int(self.source.projection_count)

    @property
    def vertex_count(self) -> int:
        return int(self.native_mesh.vertex_count)

    @property
    def polygon_count(self) -> int:
        return int(self.native_mesh.polygon_count)

    @property
    def index_count(self) -> int:
        return int(self.native_mesh.index_count)

    @property
    def occupied_voxels(self) -> int:
        return int(self.volume.occupied_count)

    @property
    def volume_dimensions(self) -> tuple[int, int, int]:
        return (int(self.volume.width), int(self.volume.depth), int(self.volume.height))


def require_native_visual_hull_output(
    context: PipelineContext,
) -> NativeVisualHullOutput:
    """
    Native-only typed accessor.

    Keep this helper for implementation-specific tools.

    Generic downstream stages such as MATERIAL should migrate
    to:

        require_geometry_surface_output(context)

    from core.geometry_contracts.
    """
    output = context.require_output(PipelineStage.GEOMETRY)
    if not isinstance(output, NativeVisualHullOutput):
        raise TypeError(
            f'GEOMETRY output is incompatible with "{IMPLEMENTATION_ID}". Expected NativeVisualHullOutput, received {type(output).__name__}.'
        )
    return output
