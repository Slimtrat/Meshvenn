from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import bpy

from ...core.geometry_contracts import GeometryProjectionSpace, GeometrySurfaceOutput
from ...core.pipeline_contracts import PipelineContext, PipelineStage
from ...core.sdf import SDFBuildResult
from ...core.sdf_surface import SDFSurfaceResult
from .config import IMPLEMENTATION_ID, SDFReconstructionConfig

# =========================================================
# Output
# =========================================================

@dataclass(
    frozen=True,
    init=False,
)
class SDFReconstructionOutput(
    GeometrySurfaceOutput
):
    """
    GEOMETRY result produced by SDF Reconstruction V1.

    Generic consumers only need the inherited:

        blender_object
        source
        projection_space
        implementation_id
        metrics
        metadata

    SDF-specific diagnostics additionally expose:

        sdf_result
        surface_result
        config

    MATERIAL must not depend on these SDF-specific fields.
    """

    sdf_result: SDFBuildResult

    surface_result: SDFSurfaceResult

    config: SDFReconstructionConfig

    normalized_height: bool

    target_height: float | None

    normalization_scale: float

    def __init__(
        self,
        *,
        blender_object: bpy.types.Object,
        source: Any,
        projection_space: GeometryProjectionSpace,
        sdf_result: SDFBuildResult,
        surface_result: SDFSurfaceResult,
        config: SDFReconstructionConfig,
        normalized_height: bool,
        target_height: float | None,
        normalization_scale: float,
        metrics: (
            Mapping[
                str,
                Any,
            ]
            | None
        ) = None,
        metadata: (
            Mapping[
                str,
                Any,
            ]
            | None
        ) = None,
    ) -> None:
        if not isinstance(
            sdf_result,
            SDFBuildResult,
        ):
            raise TypeError(
                (
                    "sdf_result must be "
                    "SDFBuildResult."
                )
            )

        if not isinstance(
            surface_result,
            SDFSurfaceResult,
        ):
            raise TypeError(
                (
                    "surface_result must be "
                    "SDFSurfaceResult."
                )
            )

        if not isinstance(
            config,
            SDFReconstructionConfig,
        ):
            raise TypeError(
                (
                    "config must be "
                    "SDFReconstructionConfig."
                )
            )

        normalization_scale = float(
            normalization_scale
        )

        if (
            not math.isfinite(
                normalization_scale
            )
            or normalization_scale
            <= 0.0
        ):
            raise ValueError(
                (
                    "normalization_scale must "
                    "be finite and positive."
                )
            )

        normalized_height = bool(
            normalized_height
        )

        resolved_target_height = (
            None
        )

        if target_height is not None:
            resolved_target_height = float(
                target_height
            )

            if (
                not math.isfinite(
                    resolved_target_height
                )
                or resolved_target_height
                <= 0.0
            ):
                raise ValueError(
                    (
                        "target_height must "
                        "be finite and positive."
                    )
                )

        if (
            normalized_height
            and resolved_target_height
            is None
        ):
            raise ValueError(
                (
                    "target_height is required "
                    "when normalized_height "
                    "is enabled."
                )
            )

        resolved_metrics = dict(
            metrics
            or {}
        )

        resolved_metrics.setdefault(
            "projection_count",
            int(
                sdf_result
                .stats
                .projection_count
            ),
        )

        resolved_metrics.setdefault(
            "sample_count",
            int(
                sdf_result
                .stats
                .voxel_count
            ),
        )

        resolved_metrics.setdefault(
            "vertex_count",
            int(
                surface_result
                .mesh
                .vertex_count
            ),
        )

        resolved_metrics.setdefault(
            "polygon_count",
            int(
                surface_result
                .mesh
                .polygon_count
            ),
        )

        resolved_metrics.setdefault(
            "normalization_scale",
            normalization_scale,
        )

        resolved_metadata = dict(
            metadata
            or {}
        )

        resolved_metadata.setdefault(
            "algorithm",
            "signed-distance-field",
        )

        resolved_metadata.setdefault(
            "surface_extractor",
            "surface-nets",
        )

        resolved_metadata.setdefault(
            "backend",
            "python-reference",
        )

        GeometrySurfaceOutput.__init__(
            self,

            blender_object=(
                blender_object
            ),

            source=source,

            projection_space=(
                projection_space
            ),

            implementation_id=(
                IMPLEMENTATION_ID
            ),

            metrics=(
                resolved_metrics
            ),

            metadata=(
                resolved_metadata
            ),
        )

        object.__setattr__(
            self,
            "sdf_result",
            sdf_result,
        )

        object.__setattr__(
            self,
            "surface_result",
            surface_result,
        )

        object.__setattr__(
            self,
            "config",
            config,
        )

        object.__setattr__(
            self,
            "normalized_height",
            normalized_height,
        )

        object.__setattr__(
            self,
            "target_height",
            resolved_target_height,
        )

        object.__setattr__(
            self,
            "normalization_scale",
            normalization_scale,
        )

    @property
    def sdf_volume(
        self,
    ):
        return (
            self.sdf_result
            .volume
        )

    @property
    def surface_mesh(
        self,
    ):
        return (
            self.surface_result
            .mesh
        )

    @property
    def projection_count(
        self,
    ) -> int:
        return int(
            self.sdf_result
            .stats
            .projection_count
        )

    @property
    def vertex_count(
        self,
    ) -> int:
        return int(
            self.surface_result
            .mesh
            .vertex_count
        )

    @property
    def polygon_count(
        self,
    ) -> int:
        return int(
            self.surface_result
            .mesh
            .polygon_count
        )

    @property
    def quad_count(
        self,
    ) -> int:
        return int(
            self.surface_result
            .mesh
            .quad_count
        )
