from __future__ import annotations

import math

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpy

from ..core.native_bridge import (
    NativeCore,
    NativeMesh,
    NativeVolume,
    normalize_mesh_mode,
)
from ..core.native_loader import (
    EXPECTED_ABI_VERSION,
    NativeAbiMismatchError,
    NativeLibraryLoadError,
    NativeLibraryNotFoundError,
    find_native_library,
    load_native_library,
)
from ..core.native_mesh_builder import (
    create_blender_mesh_from_native,
    shade_smooth_native_object,
)
from ..core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)

from .projection_images import (
    ProjectionImagesOutput,
    require_projection_images_output,
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

IMPLEMENTATION_ID = (
    "native-visual-hull"
)

DEFAULT_MESH_MODE = (
    "surface_nets"
)

DEFAULT_VOXEL_SIZE = 1.0

DEFAULT_CENTER_XY = True

DEFAULT_OBJECT_NAME = (
    "MeshvennScan"
)

DEFAULT_MESH_NAME = (
    "MeshvennNativeMesh"
)


# ---------------------------------------------------------
# Geometry output
# ---------------------------------------------------------

@dataclass(frozen=True)
class NativeVisualHullOutput:
    """
    Output contract of the built-in Native Visual Hull
    geometry implementation.

    The Blender object deliberately keeps its mesh vertices
    in native reconstruction coordinates.

    This is critical for downstream stages:

        GEOMETRY
            ↓
        MATERIAL

    Projected material requires:

        volume width/depth/height
        voxel_size
        center_xy
        native-local vertex coordinates

    Object-level uniform scaling is allowed because it does
    not mutate obj.data vertex coordinates.
    """

    blender_object: bpy.types.Object

    volume: NativeVolume

    native_mesh: NativeMesh

    source: ProjectionImagesOutput

    resolution: int

    symmetry_x: bool

    thread_count: int

    mesh_mode: str

    voxel_size: float

    center_xy: bool

    normalized_height: bool

    target_height: float | None

    normalization_scale: float

    @property
    def projection_count(
        self,
    ) -> int:
        return (
            self.source
            .projection_count
        )

    @property
    def vertex_count(
        self,
    ) -> int:
        return (
            self.native_mesh
            .vertex_count
        )

    @property
    def polygon_count(
        self,
    ) -> int:
        return (
            self.native_mesh
            .polygon_count
        )

    @property
    def occupied_voxels(
        self,
    ) -> int:
        return (
            self.volume
            .occupied_count
        )

    @property
    def volume_dimensions(
        self,
    ) -> tuple[
        int,
        int,
        int,
    ]:
        return (
            self.volume.width,
            self.volume.depth,
            self.volume.height,
        )

    @property
    def object_name(
        self,
    ) -> str:
        return str(
            self.blender_object.name
        )


# ---------------------------------------------------------
# Context helpers
# ---------------------------------------------------------

def _resolve_settings(
    context: PipelineContext,
) -> Any:
    if context.settings is not None:
        return (
            context.settings
        )

    scene = context.scene

    if scene is None:
        return None

    return getattr(
        scene,
        "bpt_settings",
        None,
    )


def require_native_visual_hull_output(
    context: PipelineContext,
) -> NativeVisualHullOutput:
    """
    Typed accessor for downstream built-in stages.
    """

    output = (
        context.require_output(
            PipelineStage.GEOMETRY
        )
    )

    if not isinstance(
        output,
        NativeVisualHullOutput,
    ):
        raise TypeError(
            (
                "GEOMETRY output is incompatible with "
                f'"{IMPLEMENTATION_ID}". Expected '
                "NativeVisualHullOutput, received "
                f"{type(output).__name__}."
            )
        )

    return output


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

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

    def validate(
        self,
    ) -> None:
        if (
            self.resolution < 16
            or self.resolution > 256
        ):
            raise ValueError(
                (
                    "Resolution must be between "
                    "16 and 256."
                )
            )

        if self.thread_count < 0:
            raise ValueError(
                (
                    "Thread count cannot "
                    "be negative."
                )
            )

        if (
            not math.isfinite(
                self.voxel_size
            )
            or self.voxel_size <= 0.0
        ):
            raise ValueError(
                (
                    "Voxel size must be finite "
                    "and greater than zero."
                )
            )

        if (
            not math.isfinite(
                self.target_height
            )
            or self.target_height <= 0.0
        ):
            raise ValueError(
                (
                    "Target height must be finite "
                    "and greater than zero."
                )
            )

        normalize_mesh_mode(
            self.mesh_mode
        )


def _config_from_settings(
    settings: Any,
) -> NativeVisualHullConfig:
    """
    Resolve implementation configuration from current
    Blender settings.

    mesh_mode and voxel_size are read defensively so this
    adapter already supports future implementation-specific
    PropertyGroups without breaking the current settings
    model.
    """

    mesh_mode = str(
        getattr(
            settings,
            "mesh_mode",
            DEFAULT_MESH_MODE,
        )
    )

    voxel_size = float(
        getattr(
            settings,
            "voxel_size",
            DEFAULT_VOXEL_SIZE,
        )
    )

    config = (
        NativeVisualHullConfig(
            resolution=int(
                settings.resolution
            ),
            symmetry_x=bool(
                settings.symmetry_x
            ),
            thread_count=int(
                settings.thread_count
            ),
            mesh_mode=(
                mesh_mode
            ),
            voxel_size=(
                voxel_size
            ),
            center_xy=(
                DEFAULT_CENTER_XY
            ),
            normalize_height=bool(
                settings.normalize_height
            ),
            target_height=float(
                settings.target_height
            ),
        )
    )

    config.validate()

    return config


# ---------------------------------------------------------
# Native availability
# ---------------------------------------------------------

def _native_library_availability(
) -> ImplementationAvailability:
    """
    Validate both presence and ABI of the native library.

    This gives the general pipeline UI a useful READY /
    UNAVAILABLE state without knowing anything about ctypes.
    """

    try:
        path = (
            find_native_library()
        )

        library = (
            load_native_library(
                path
            )
        )

        abi_version = int(
            library
            .bpt_abi_version()
        )

    except NativeLibraryNotFoundError as exc:
        return (
            ImplementationAvailability
            .unavailable(
                "Native C++ library not found.",
                details={
                    "error": str(
                        exc
                    ),
                },
            )
        )

    except NativeAbiMismatchError as exc:
        return (
            ImplementationAvailability
            .unavailable(
                "Native C++ ABI mismatch.",
                details={
                    "expected_abi": (
                        EXPECTED_ABI_VERSION
                    ),
                    "error": str(
                        exc
                    ),
                },
            )
        )

    except NativeLibraryLoadError as exc:
        return (
            ImplementationAvailability
            .unavailable(
                (
                    "Native C++ library "
                    "could not be loaded."
                ),
                details={
                    "error": str(
                        exc
                    ),
                },
            )
        )

    except Exception as exc:
        return (
            ImplementationAvailability
            .unavailable(
                (
                    "Native C++ engine "
                    "availability check failed."
                ),
                details={
                    "exception_type": (
                        type(exc).__name__
                    ),
                    "error": str(
                        exc
                    ),
                },
            )
        )

    return (
        ImplementationAvailability
        .ready_state(
            details={
                "library": str(
                    path
                ),
                "abi": (
                    abi_version
                ),
            }
        )
    )


# ---------------------------------------------------------
# Blender helpers
# ---------------------------------------------------------

def _remove_blender_object(
    obj: bpy.types.Object | None,
) -> None:
    """
    Remove a partially-created geometry object when the
    implementation fails after Blender injection.
    """

    if obj is None:
        return

    mesh = (
        obj.data
        if (
            obj.type == "MESH"
            and obj.data is not None
        )
        else None
    )

    try:
        bpy.data.objects.remove(
            obj,
            do_unlink=True,
        )

    finally:
        if (
            mesh is not None
            and mesh.users == 0
        ):
            bpy.data.meshes.remove(
                mesh
            )


def _apply_non_destructive_height_normalization(
    obj: bpy.types.Object,
    *,
    enabled: bool,
    target_height: float,
) -> float:
    """
    Normalize visible object height without altering local
    mesh coordinates.

    Why object.scale instead of obj.data.transform():

        projected_material.py works in native reconstruction
        coordinates.

    GEOMETRY runs before MATERIAL, therefore applying scale
    directly to vertex coordinates here would invalidate
    material projection.

    Uniform object scale preserves:

        vertex.co
        native BVH coordinates
        visual-hull projection space

    while presenting the requested final size in Blender.

    The transform may be applied later by a rig/export
    implementation once projection-dependent stages are done.
    """

    if not enabled:
        return 1.0

    if (
        not math.isfinite(
            target_height
        )
        or target_height <= 0.0
    ):
        raise ValueError(
            (
                "Target height must be finite "
                "and greater than zero."
            )
        )

    current_height = float(
        obj.dimensions.z
    )

    if (
        not math.isfinite(
            current_height
        )
        or current_height <= 0.0
    ):
        return 1.0

    factor = (
        target_height
        / current_height
    )

    obj.scale.x *= factor
    obj.scale.y *= factor
    obj.scale.z *= factor

    if (
        bpy.context.view_layer
        is not None
    ):
        bpy.context.view_layer.update()

    return float(
        factor
    )


# ---------------------------------------------------------
# Metadata
# ---------------------------------------------------------

def _write_geometry_metadata(
    obj: bpy.types.Object,
    *,
    source: ProjectionImagesOutput,
    volume: NativeVolume,
    native_mesh: NativeMesh,
    config: NativeVisualHullConfig,
    normalization_scale: float,
) -> None:
    """
    Preserve existing BPT metadata while adding pipeline
    identity.

    Existing consumers therefore continue to work while the
    UI migrates to the generic architecture.
    """

    # -----------------------------------------------------
    # Generic pipeline metadata
    # -----------------------------------------------------

    obj[
        "meshvenn_geometry_implementation"
    ] = (
        IMPLEMENTATION_ID
    )

    obj[
        "meshvenn_geometry_version"
    ] = "1"

    obj[
        "meshvenn_native_space_preserved"
    ] = True

    obj[
        "meshvenn_normalization_scale"
    ] = float(
        normalization_scale
    )

    # -----------------------------------------------------
    # Historical/public BPT metadata
    # -----------------------------------------------------

    obj[
        "bpt_engine"
    ] = "native-cpp"

    obj[
        "bpt_mesh_mode"
    ] = (
        config.mesh_mode
    )

    obj[
        "bpt_projection_count"
    ] = (
        source.projection_count
    )

    obj[
        "bpt_resolution"
    ] = (
        config.resolution
    )

    obj[
        "bpt_threads"
    ] = (
        config.thread_count
    )

    obj[
        "bpt_symmetry_x"
    ] = (
        config.symmetry_x
    )

    obj[
        "bpt_voxel_size"
    ] = (
        config.voxel_size
    )

    obj[
        "bpt_center_xy"
    ] = (
        config.center_xy
    )

    obj[
        "bpt_occupied_voxels"
    ] = (
        volume.occupied_count
    )

    obj[
        "bpt_native_vertices"
    ] = (
        native_mesh.vertex_count
    )

    obj[
        "bpt_native_polygons"
    ] = (
        native_mesh.polygon_count
    )

    obj[
        "bpt_native_indices"
    ] = (
        native_mesh.index_count
    )

    obj[
        "bpt_normalize_height"
    ] = (
        config.normalize_height
    )

    if config.normalize_height:
        obj[
            "bpt_target_height"
        ] = (
            config.target_height
        )


# ---------------------------------------------------------
# Implementation
# ---------------------------------------------------------

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
        NativeVisualHullOutput

    No material logic belongs here.
    """

    _descriptor = (
        ImplementationDescriptor(
            identifier=(
                IMPLEMENTATION_ID
            ),
            stage=(
                PipelineStage.GEOMETRY
            ),
            label="Native Visual Hull",
            description=(
                "Reconstruct a 3D mesh from silhouette "
                "projections using the native C++ visual "
                "hull engine."
            ),
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
            ),
        )
    )

    @property
    def descriptor(
        self,
    ) -> ImplementationDescriptor:
        return (
            self._descriptor
        )

    # -----------------------------------------------------
    # Availability
    # -----------------------------------------------------

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        settings = (
            _resolve_settings(
                context
            )
        )

        if settings is None:
            return (
                ImplementationAvailability
                .unavailable(
                    "Meshvenn settings are unavailable."
                )
            )

        # -------------------------------------------------
        # INPUT must already exist when this is called by
        # PipelineRunner.
        # -------------------------------------------------

        try:
            source = (
                require_projection_images_output(
                    context
                )
            )

        except Exception as exc:
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "Prepared projection input "
                        "is unavailable."
                    ),
                    details={
                        "error": str(
                            exc
                        ),
                    },
                )
            )

        if source.projection_count < 2:
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "At least two prepared "
                        "projections are required."
                    ),
                    details={
                        "projection_count": (
                            source.projection_count
                        ),
                    },
                )
            )

        try:
            config = (
                _config_from_settings(
                    settings
                )
            )

        except Exception as exc:
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "Native Visual Hull "
                        "configuration is invalid."
                    ),
                    details={
                        "error": str(
                            exc
                        ),
                    },
                )
            )

        native_status = (
            _native_library_availability()
        )

        if not native_status.available:
            return native_status

        details = dict(
            native_status.details
        )

        details.update(
            {
                "projection_count": (
                    source.projection_count
                ),
                "resolution": (
                    config.resolution
                ),
                "mesh_mode": (
                    config.mesh_mode
                ),
                "thread_count": (
                    config.thread_count
                ),
                "symmetry_x": (
                    config.symmetry_x
                ),
            }
        )

        if source.empty_mask_count > 0:
            return (
                ImplementationAvailability
                .degraded(
                    (
                        f"{source.empty_mask_count} prepared "
                        "projection mask"
                        + (
                            "s are"
                            if source.empty_mask_count != 1
                            else " is"
                        )
                        + " empty. The resulting visual "
                        "hull may intentionally be empty."
                    ),
                    details=(
                        details
                    ),
                )
            )

        return (
            ImplementationAvailability
            .ready_state(
                details=(
                    details
                )
            )
        )

    # -----------------------------------------------------
    # Execute
    # -----------------------------------------------------

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        settings = (
            _resolve_settings(
                context
            )
        )

        if settings is None:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "Meshvenn settings are unavailable."
                    ),
                )
            )

        try:
            source = (
                require_projection_images_output(
                    context
                )
            )

        except Exception as exc:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "Prepared projection input "
                        f"is unavailable: {exc}"
                    ),
                )
            )

        if source.projection_count < 2:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "At least two prepared "
                        "projections are required."
                    ),
                    metadata={
                        "projection_count": (
                            source.projection_count
                        ),
                    },
                )
            )

        try:
            config = (
                _config_from_settings(
                    settings
                )
            )

        except Exception as exc:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    message=(
                        "Invalid Native Visual Hull "
                        f"configuration: {exc}"
                    ),
                    metadata={
                        "exception_type": (
                            type(exc).__name__
                        ),
                    },
                )
            )

        obj: (
            bpy.types.Object
            | None
        ) = None

        try:
            # -------------------------------------------------
            # Native engine
            # -------------------------------------------------

            core = (
                NativeCore()
            )

            # -------------------------------------------------
            # Visual hull
            #
            # Empty masks are NOT discarded here.
            # If an enabled silhouette is empty, the correct
            # mathematical result may be an empty hull.
            # -------------------------------------------------

            volume = (
                core.build_visual_hull(
                    source.native_projections,
                    resolution=(
                        config.resolution
                    ),
                    symmetry_x=(
                        config.symmetry_x
                    ),
                    thread_count=(
                        config.thread_count
                    ),
                )
            )

            if (
                volume.occupied_count
                == 0
            ):
                return (
                    StageExecutionResult
                    .failed_result(
                        stage=(
                            PipelineStage.GEOMETRY
                        ),
                        implementation_id=(
                            IMPLEMENTATION_ID
                        ),
                        message=(
                            "The projections produced "
                            "an empty visual hull."
                        ),
                        metadata={
                            "projection_count": (
                                source
                                .projection_count
                            ),
                            "empty_masks": (
                                source
                                .empty_mask_count
                            ),
                            "resolution": (
                                config.resolution
                            ),
                        },
                    )
                )

            # -------------------------------------------------
            # Surface extraction
            # -------------------------------------------------

            native_mesh = (
                core.build_surface_mesh(
                    volume,
                    voxel_size=(
                        config.voxel_size
                    ),
                    center_xy=(
                        config.center_xy
                    ),
                    mesh_mode=(
                        config.mesh_mode
                    ),
                )
            )

            if (
                native_mesh.vertex_count
                <= 0
            ):
                return (
                    StageExecutionResult
                    .failed_result(
                        stage=(
                            PipelineStage.GEOMETRY
                        ),
                        implementation_id=(
                            IMPLEMENTATION_ID
                        ),
                        message=(
                            "Native mesh extraction "
                            "returned no vertices."
                        ),
                        metadata={
                            "occupied_voxels": (
                                volume
                                .occupied_count
                            ),
                            "mesh_mode": (
                                config.mesh_mode
                            ),
                        },
                    )
                )

            if (
                native_mesh.polygon_count
                <= 0
            ):
                return (
                    StageExecutionResult
                    .failed_result(
                        stage=(
                            PipelineStage.GEOMETRY
                        ),
                        implementation_id=(
                            IMPLEMENTATION_ID
                        ),
                        message=(
                            "Native mesh extraction "
                            "returned no polygons."
                        ),
                        metadata={
                            "vertices": (
                                native_mesh
                                .vertex_count
                            ),
                            "mesh_mode": (
                                config.mesh_mode
                            ),
                        },
                    )
                )

            # -------------------------------------------------
            # Blender injection
            # -------------------------------------------------

            obj = (
                create_blender_mesh_from_native(
                    native_mesh,
                    mesh_name=(
                        DEFAULT_MESH_NAME
                    ),
                    object_name=(
                        DEFAULT_OBJECT_NAME
                    ),
                )
            )

            # -------------------------------------------------
            # Smooth normals
            #
            # MATERIAL V1.2 scores projection candidates from
            # these normals, so they must be available before
            # the next pipeline stage executes.
            # -------------------------------------------------

            shade_smooth_native_object(
                obj
            )

            # -------------------------------------------------
            # Non-destructive normalization
            #
            # DO NOT apply the scale to obj.data here.
            #
            # Material projection still requires the local
            # vertices to exactly match native reconstruction
            # coordinates.
            # -------------------------------------------------

            normalization_scale = (
                _apply_non_destructive_height_normalization(
                    obj,
                    enabled=(
                        config
                        .normalize_height
                    ),
                    target_height=(
                        config
                        .target_height
                    ),
                )
            )

            # -------------------------------------------------
            # Metadata
            # -------------------------------------------------

            _write_geometry_metadata(
                obj,
                source=source,
                volume=volume,
                native_mesh=(
                    native_mesh
                ),
                config=config,
                normalization_scale=(
                    normalization_scale
                ),
            )

            # -------------------------------------------------
            # Pipeline output
            # -------------------------------------------------

            output = (
                NativeVisualHullOutput(
                    blender_object=(
                        obj
                    ),
                    volume=volume,
                    native_mesh=(
                        native_mesh
                    ),
                    source=source,
                    resolution=(
                        config.resolution
                    ),
                    symmetry_x=(
                        config.symmetry_x
                    ),
                    thread_count=(
                        config.thread_count
                    ),
                    mesh_mode=(
                        config.mesh_mode
                    ),
                    voxel_size=(
                        config.voxel_size
                    ),
                    center_xy=(
                        config.center_xy
                    ),
                    normalized_height=(
                        config
                        .normalize_height
                    ),
                    target_height=(
                        config.target_height
                        if (
                            config
                            .normalize_height
                        )
                        else None
                    ),
                    normalization_scale=(
                        normalization_scale
                    ),
                )
            )

            # -------------------------------------------------
            # Lightweight global context metadata
            # -------------------------------------------------

            context.metadata[
                "geometry_object_name"
            ] = (
                obj.name
            )

            context.metadata[
                "geometry_mesh_mode"
            ] = (
                config.mesh_mode
            )

            context.metadata[
                "geometry_occupied_voxels"
            ] = (
                volume.occupied_count
            )

            # Ownership has now transferred to the pipeline.
            #
            # Do not clean `obj` if anything below succeeds.
            created_object = obj

            return (
                StageExecutionResult
                .succeeded(
                    stage=(
                        PipelineStage.GEOMETRY
                    ),
                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),
                    payload=output,
                    message=(
                        "Native visual hull generated: "
                        f"{volume.occupied_count} voxels, "
                        f"{native_mesh.vertex_count} vertices, "
                        f"{native_mesh.polygon_count} polygons."
                    ),
                    metrics={
                        "projections": (
                            source
                            .projection_count
                        ),
                        "resolution": (
                            config.resolution
                        ),
                        "occupied_voxels": (
                            volume
                            .occupied_count
                        ),
                        "vertices": (
                            native_mesh
                            .vertex_count
                        ),
                        "indices": (
                            native_mesh
                            .index_count
                        ),
                        "polygons": (
                            native_mesh
                            .polygon_count
                        ),
                        "normalization_scale": (
                            normalization_scale
                        ),
                    },
                    metadata={
                        "object_name": (
                            created_object
                            .name
                        ),
                        "mesh_name": (
                            created_object
                            .data
                            .name
                        ),
                        "mesh_mode": (
                            config.mesh_mode
                        ),
                        "voxel_size": (
                            config.voxel_size
                        ),
                        "center_xy": (
                            config.center_xy
                        ),
                        "symmetry_x": (
                            config.symmetry_x
                        ),
                        "thread_count": (
                            config.thread_count
                        ),
                        "volume": {
                            "width": (
                                volume.width
                            ),
                            "depth": (
                                volume.depth
                            ),
                            "height": (
                                volume.height
                            ),
                            "bounds": (
                                list(
                                    volume.bounds
                                )
                                if (
                                    volume.bounds
                                    is not None
                                )
                                else None
                            ),
                        },
                        "normalize_height": (
                            config
                            .normalize_height
                        ),
                        "target_height": (
                            config.target_height
                            if (
                                config
                                .normalize_height
                            )
                            else None
                        ),
                        "native_local_coordinates_preserved": (
                            True
                        ),
                    },
                )
            )

        except Exception:
            # -------------------------------------------------
            # A Blender object which has already been injected
            # must not survive a failed GEOMETRY stage.
            #
            # PipelineRunner will convert the exception into a
            # FAILED StageExecutionResult.
            # -------------------------------------------------

            _remove_blender_object(
                obj
            )

            raise