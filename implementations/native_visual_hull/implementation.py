from __future__ import annotations
import bpy
from ...core.native_bridge import NativeCore
from ...core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..projection_images import require_projection_images_output
from .availability import _native_library_availability
from .blender_output import (
    _apply_non_destructive_height_normalization,
    _remove_blender_object,
    _write_geometry_metadata,
)
from .config import (
    _config_from_settings,
    _projection_space_from_volume,
    _resolve_settings,
)
from .constants import DEFAULT_MESH_NAME, DEFAULT_OBJECT_NAME, IMPLEMENTATION_ID
from .output import NativeVisualHullOutput
from .execution import execute_native_visual_hull


class NativeVisualHullImplementation:
    """
    Built-in GEOMETRY implementation.

        ProjectionImagesOutput
                ↓
        Native C++ visual hull
                ↓
        NativeVolume
                ↓
        Surface Nets / Blocks
                ↓
        NativeMesh
                ↓
        Blender Mesh Object
                ↓
        GeometryProjectionSpace
                ↓
        NativeVisualHullOutput
                │
                └── GeometrySurfaceOutput

    No material logic belongs here.
    """

    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.GEOMETRY,
        label="Native Visual Hull",
        description="Reconstruct a 3D mesh from silhouette projections using the native C++ visual hull engine.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "visual-hull",
            "native-cpp",
            "surface-nets",
            "voxel-blocks",
            "symmetry-x",
            "multithreaded",
            "geometry-surface-output",
            "projection-space",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        settings = _resolve_settings(context)
        if settings is None:
            return ImplementationAvailability.unavailable(
                "Meshvenn settings are unavailable."
            )
        try:
            source = require_projection_images_output(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(
                "Prepared projection input is unavailable.", details={"error": str(exc)}
            )
        if source.projection_count < 2:
            return ImplementationAvailability.unavailable(
                "At least two prepared projections are required.",
                details={"projection_count": source.projection_count},
            )
        try:
            config = _config_from_settings(settings)
        except Exception as exc:
            return ImplementationAvailability.unavailable(
                "Native Visual Hull configuration is invalid.",
                details={"error": str(exc)},
            )
        native_status = _native_library_availability()
        if not native_status.available:
            return native_status
        details = dict(native_status.details)
        details.update(
            {
                "projection_count": source.projection_count,
                "resolution": config.resolution,
                "mesh_mode": config.mesh_mode,
                "thread_count": config.thread_count,
                "symmetry_x": config.symmetry_x,
                "geometry_contract": "surface-output-v1",
            }
        )
        if source.empty_mask_count > 0:
            return ImplementationAvailability.degraded(
                f"{source.empty_mask_count} prepared projection mask"
                + ("s are" if source.empty_mask_count != 1 else " is")
                + " empty. The resulting visual hull may intentionally be empty.",
                details=details,
            )
        return ImplementationAvailability.ready_state(details=details)

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        return execute_native_visual_hull(context)
