from __future__ import annotations

import math

from dataclasses import dataclass
from typing import (
    Any,
    Mapping,
)

import bpy

from ..core.geometry_contracts import (
    GeometryProjectionSpace,
    GeometrySurfaceOutput,
)
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


# =========================================================
# Constants
# =========================================================

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


# =========================================================
# Geometry output
# =========================================================

@dataclass(
    frozen=True,
    init=False,
)
class NativeVisualHullOutput(
    GeometrySurfaceOutput
):
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
        projection_space: (
            GeometryProjectionSpace
            | None
        ) = None,

        # -------------------------------------------------
        # Temporary legacy constructor compatibility.
        # -------------------------------------------------

        voxel_size: float | None = None,
        center_xy: bool | None = None,

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
        if volume is None:
            raise ValueError(
                (
                    "NativeVisualHullOutput "
                    "requires a NativeVolume."
                )
            )

        if native_mesh is None:
            raise ValueError(
                (
                    "NativeVisualHullOutput "
                    "requires a NativeMesh."
                )
            )

        # -------------------------------------------------
        # Normalize implementation-specific values.
        # -------------------------------------------------

        normalized_resolution = int(
            resolution
        )

        if (
            normalized_resolution < 16
            or normalized_resolution > 256
        ):
            raise ValueError(
                (
                    "Resolution must be between "
                    "16 and 256."
                )
            )

        normalized_thread_count = int(
            thread_count
        )

        if normalized_thread_count < 0:
            raise ValueError(
                (
                    "Thread count cannot "
                    "be negative."
                )
            )

        normalized_mesh_mode = (
            normalize_mesh_mode(
                str(
                    mesh_mode
                )
            )
        )

        normalized_scale = float(
            normalization_scale
        )

        if (
            not math.isfinite(
                normalized_scale
            )
            or normalized_scale <= 0.0
        ):
            raise ValueError(
                (
                    "normalization_scale must "
                    "be finite and greater "
                    "than zero."
                )
            )

        normalized_height_flag = bool(
            normalized_height
        )

        normalized_target_height = (
            None
        )

        if target_height is not None:
            normalized_target_height = float(
                target_height
            )

            if (
                not math.isfinite(
                    normalized_target_height
                )
                or normalized_target_height
                <= 0.0
            ):
                raise ValueError(
                    (
                        "target_height must "
                        "be finite and greater "
                        "than zero."
                    )
                )

        if (
            normalized_height_flag
            and normalized_target_height
            is None
        ):
            raise ValueError(
                (
                    "target_height is required "
                    "when normalized_height "
                    "is enabled."
                )
            )

        # -------------------------------------------------
        # Resolve generic projection space.
        #
        # No strict isinstance check is intentionally made
        # against NativeVolume / NativeMesh.
        #
        # Some diagnostic scripts load the same source code
        # under a second package namespace. Duck typing here
        # preserves those tooling paths during migration.
        # -------------------------------------------------

        volume_width = int(
            volume.width
        )

        volume_depth = int(
            volume.depth
        )

        volume_height = int(
            volume.height
        )

        if projection_space is None:
            resolved_voxel_size = (
                DEFAULT_VOXEL_SIZE
                if voxel_size is None
                else float(
                    voxel_size
                )
            )

            resolved_center_xy = (
                DEFAULT_CENTER_XY
                if center_xy is None
                else bool(
                    center_xy
                )
            )

            projection_space = (
                GeometryProjectionSpace(
                    width=(
                        volume_width
                    ),
                    depth=(
                        volume_depth
                    ),
                    height=(
                        volume_height
                    ),
                    voxel_size=(
                        resolved_voxel_size
                    ),
                    center_xy=(
                        resolved_center_xy
                    ),
                )
            )

        else:
            if not isinstance(
                projection_space,
                GeometryProjectionSpace,
            ):
                raise TypeError(
                    (
                        "projection_space must "
                        "be a "
                        "GeometryProjectionSpace."
                    )
                )

            # ---------------------------------------------
            # Native volume and generic projection space
            # must describe the same reconstruction domain.
            # ---------------------------------------------

            expected_dimensions = (
                volume_width,
                volume_depth,
                volume_height,
            )

            if (
                projection_space.dimensions
                != expected_dimensions
            ):
                raise ValueError(
                    (
                        "Projection-space dimensions "
                        "do not match NativeVolume.\n"
                        f"Projection space: "
                        f"{projection_space.dimensions}\n"
                        f"Native volume:    "
                        f"{expected_dimensions}"
                    )
                )

            # ---------------------------------------------
            # If a legacy caller supplies both new and old
            # arguments, reject contradictory values rather
            # than silently choosing one.
            # ---------------------------------------------

            if voxel_size is not None:
                legacy_voxel_size = float(
                    voxel_size
                )

                if not math.isclose(
                    legacy_voxel_size,
                    projection_space
                    .voxel_size,
                    rel_tol=1e-9,
                    abs_tol=1e-9,
                ):
                    raise ValueError(
                        (
                            "Legacy voxel_size does "
                            "not match projection_space."
                        )
                    )

            if (
                center_xy is not None
                and bool(
                    center_xy
                )
                != projection_space.center_xy
            ):
                raise ValueError(
                    (
                        "Legacy center_xy does "
                        "not match projection_space."
                    )
                )

        # -------------------------------------------------
        # Generic metrics.
        #
        # These are convenience diagnostics only.
        # Fundamental projection information stays in the
        # explicit GeometryProjectionSpace contract.
        # -------------------------------------------------

        resolved_metrics = dict(
            metrics
            or {}
        )

        resolved_metrics.setdefault(
            "projection_count",
            int(
                source.projection_count
            ),
        )

        resolved_metrics.setdefault(
            "resolution",
            normalized_resolution,
        )

        resolved_metrics.setdefault(
            "occupied_voxels",
            int(
                volume.occupied_count
            ),
        )

        resolved_metrics.setdefault(
            "vertex_count",
            int(
                native_mesh.vertex_count
            ),
        )

        resolved_metrics.setdefault(
            "index_count",
            int(
                native_mesh.index_count
            ),
        )

        resolved_metrics.setdefault(
            "polygon_count",
            int(
                native_mesh.polygon_count
            ),
        )

        resolved_metrics.setdefault(
            "normalization_scale",
            normalized_scale,
        )

        resolved_metadata = dict(
            metadata
            or {}
        )

        resolved_metadata.setdefault(
            "mesh_mode",
            normalized_mesh_mode,
        )

        resolved_metadata.setdefault(
            "symmetry_x",
            bool(
                symmetry_x
            ),
        )

        resolved_metadata.setdefault(
            "thread_count",
            normalized_thread_count,
        )

        resolved_metadata.setdefault(
            "normalized_height",
            normalized_height_flag,
        )

        resolved_metadata.setdefault(
            "target_height",
            normalized_target_height,
        )

        # -------------------------------------------------
        # Initialize generic base contract.
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Native specialization.
        # -------------------------------------------------

        object.__setattr__(
            self,
            "volume",
            volume,
        )

        object.__setattr__(
            self,
            "native_mesh",
            native_mesh,
        )

        object.__setattr__(
            self,
            "resolution",
            normalized_resolution,
        )

        object.__setattr__(
            self,
            "symmetry_x",
            bool(
                symmetry_x
            ),
        )

        object.__setattr__(
            self,
            "thread_count",
            normalized_thread_count,
        )

        object.__setattr__(
            self,
            "mesh_mode",
            normalized_mesh_mode,
        )

        object.__setattr__(
            self,
            "normalized_height",
            normalized_height_flag,
        )

        object.__setattr__(
            self,
            "target_height",
            normalized_target_height,
        )

        object.__setattr__(
            self,
            "normalization_scale",
            normalized_scale,
        )

    # -----------------------------------------------------
    # Native diagnostics
    # -----------------------------------------------------

    @property
    def projection_count(
        self,
    ) -> int:
        return int(
            self.source
            .projection_count
        )

    @property
    def vertex_count(
        self,
    ) -> int:
        return int(
            self.native_mesh
            .vertex_count
        )

    @property
    def polygon_count(
        self,
    ) -> int:
        return int(
            self.native_mesh
            .polygon_count
        )

    @property
    def index_count(
        self,
    ) -> int:
        return int(
            self.native_mesh
            .index_count
        )

    @property
    def occupied_voxels(
        self,
    ) -> int:
        return int(
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
            int(
                self.volume.width
            ),
            int(
                self.volume.depth
            ),
            int(
                self.volume.height
            ),
        )


# =========================================================
# Context helpers
# =========================================================

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
    Native-only typed accessor.

    Keep this helper for implementation-specific tools.

    Generic downstream stages such as MATERIAL should migrate
    to:

        require_geometry_surface_output(context)

    from core.geometry_contracts.
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


# =========================================================
# Configuration
# =========================================================

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


# =========================================================
# Projection-space construction
# =========================================================

def _projection_space_from_volume(
    volume: NativeVolume,
    config: NativeVisualHullConfig,
) -> GeometryProjectionSpace:
    """
    Adapt NativeVolume into the algorithm-neutral coordinate
    contract consumed by downstream stages.
    """

    return GeometryProjectionSpace(
        width=int(
            volume.width
        ),
        depth=int(
            volume.depth
        ),
        height=int(
            volume.height
        ),
        voxel_size=float(
            config.voxel_size
        ),
        center_xy=bool(
            config.center_xy
        ),
    )


# =========================================================
# Native availability
# =========================================================

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
                        type(
                            exc
                        )
                        .__name__
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


# =========================================================
# Blender helpers
# =========================================================

def _remove_blender_object(
    obj: (
        bpy.types.Object
        | None
    ),
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

        projection-dependent MATERIAL stages work in the
        reconstruction coordinate space.

    GEOMETRY runs before MATERIAL, therefore applying scale
    directly to vertex coordinates here would invalidate
    projection.

    Uniform object scale preserves:

        vertex.co
        native BVH coordinates
        GeometryProjectionSpace

    while presenting the requested final size in Blender.

    RIG / EXPORT may apply the transform later once
    projection-dependent stages are complete.
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


# =========================================================
# Metadata
# =========================================================

def _write_geometry_metadata(
    obj: bpy.types.Object,
    *,
    source: ProjectionImagesOutput,
    volume: NativeVolume,
    native_mesh: NativeMesh,
    projection_space: GeometryProjectionSpace,
    config: NativeVisualHullConfig,
    normalization_scale: float,
) -> None:
    """
    Preserve historical BPT metadata while exposing the new
    generic GEOMETRY contract identity.
    """

    # -----------------------------------------------------
    # Generic Meshvenn geometry metadata
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

    obj[
        "meshvenn_projection_convention"
    ] = (
        projection_space
        .convention
        .value
    )

    obj[
        "meshvenn_projection_width"
    ] = (
        projection_space.width
    )

    obj[
        "meshvenn_projection_depth"
    ] = (
        projection_space.depth
    )

    obj[
        "meshvenn_projection_height"
    ] = (
        projection_space.height
    )

    obj[
        "meshvenn_projection_voxel_size"
    ] = (
        projection_space.voxel_size
    )

    obj[
        "meshvenn_projection_center_xy"
    ] = (
        projection_space.center_xy
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


# =========================================================
# Implementation
# =========================================================

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

    _descriptor = (
        ImplementationDescriptor(
            identifier=(
                IMPLEMENTATION_ID
            ),
            stage=(
                PipelineStage.GEOMETRY
            ),
            label=(
                "Native Visual Hull"
            ),
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
                "geometry-surface-output",
                "projection-space",
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
                    (
                        "Meshvenn settings "
                        "are unavailable."
                    )
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
                            source
                            .projection_count
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
                    source
                    .projection_count
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

                "geometry_contract": (
                    "surface-output-v1"
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
                            if (
                                source
                                .empty_mask_count
                                != 1
                            )
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
                        "Meshvenn settings "
                        "are unavailable."
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
                            source
                            .projection_count
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
                            type(
                                exc
                            )
                            .__name__
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
            # Native visual hull
            # -------------------------------------------------

            core = (
                NativeCore()
            )

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
            # Projection-based materials score source views
            # using these normals.
            # -------------------------------------------------

            shade_smooth_native_object(
                obj
            )

            # -------------------------------------------------
            # Build algorithm-neutral projection space.
            # -------------------------------------------------

            projection_space = (
                _projection_space_from_volume(
                    volume,
                    config,
                )
            )

            # -------------------------------------------------
            # Non-destructive normalization
            #
            # DO NOT apply scale to obj.data here.
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
                projection_space=(
                    projection_space
                ),
                config=config,
                normalization_scale=(
                    normalization_scale
                ),
            )

            # -------------------------------------------------
            # Generic + native output metrics
            # -------------------------------------------------

            output_metrics = {
                "projection_count": (
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

                "vertex_count": (
                    native_mesh
                    .vertex_count
                ),

                "index_count": (
                    native_mesh
                    .index_count
                ),

                "polygon_count": (
                    native_mesh
                    .polygon_count
                ),

                "normalization_scale": (
                    normalization_scale
                ),
            }

            output_metadata = {
                "mesh_mode": (
                    config.mesh_mode
                ),

                "symmetry_x": (
                    config.symmetry_x
                ),

                "thread_count": (
                    config.thread_count
                ),

                "normalized_height": (
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

                "projection_convention": (
                    projection_space
                    .convention
                    .value
                ),
            }

            # -------------------------------------------------
            # Pipeline output
            # -------------------------------------------------

            output = (
                NativeVisualHullOutput(
                    blender_object=(
                        obj
                    ),

                    source=source,

                    projection_space=(
                        projection_space
                    ),

                    volume=volume,

                    native_mesh=(
                        native_mesh
                    ),

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

                    metrics=(
                        output_metrics
                    ),

                    metadata=(
                        output_metadata
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
                "geometry_implementation"
            ] = (
                IMPLEMENTATION_ID
            )

            context.metadata[
                "geometry_contract"
            ] = (
                "surface-output-v1"
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

            context.metadata[
                "geometry_projection_space"
            ] = {
                "width": (
                    projection_space.width
                ),

                "depth": (
                    projection_space.depth
                ),

                "height": (
                    projection_space.height
                ),

                "voxel_size": (
                    projection_space
                    .voxel_size
                ),

                "center_xy": (
                    projection_space
                    .center_xy
                ),

                "convention": (
                    projection_space
                    .convention
                    .value
                ),
            }

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

                        "geometry_contract": (
                            "surface-output-v1"
                        ),

                        "mesh_mode": (
                            config.mesh_mode
                        ),

                        "voxel_size": (
                            projection_space
                            .voxel_size
                        ),

                        "center_xy": (
                            projection_space
                            .center_xy
                        ),

                        "symmetry_x": (
                            config.symmetry_x
                        ),

                        "thread_count": (
                            config.thread_count
                        ),

                        "projection_space": {
                            "width": (
                                projection_space
                                .width
                            ),

                            "depth": (
                                projection_space
                                .depth
                            ),

                            "height": (
                                projection_space
                                .height
                            ),

                            "voxel_size": (
                                projection_space
                                .voxel_size
                            ),

                            "center_xy": (
                                projection_space
                                .center_xy
                            ),

                            "convention": (
                                projection_space
                                .convention
                                .value
                            ),
                        },

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
            # A Blender object already injected must not
            # survive a failed GEOMETRY stage.
            # -------------------------------------------------

            _remove_blender_object(
                obj
            )

            raise