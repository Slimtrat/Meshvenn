from __future__ import annotations

import math

from array import array
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
from ..core.image_mask import (
    BinaryMask,
)
from ..core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..core.sdf import (
    DEFAULT_ISO_LEVEL,
    DEFAULT_REFERENCE_MAX_VOXELS,
    DEFAULT_SMOOTHNESS,
    DEFAULT_SURFACE_OFFSET,
    SDFBuildConfig,
    SDFBuildProgress,
    SDFBuildResult,
    build_sdf_from_views,
)
from ..core.sdf_surface import (
    DEFAULT_GRADIENT_STEP_SCALE,
    SDFSurfaceConfig,
    SDFSurfaceResult,
    extract_surface_nets,
)


# =========================================================
# Constants
# =========================================================

IMPLEMENTATION_ID = (
    "sdf-reconstruction-v1"
)

IMPLEMENTATION_VERSION = (
    "1"
)


DEFAULT_RESOLUTION = 96

MINIMUM_RESOLUTION = 16

MAXIMUM_RESOLUTION = 256


DEFAULT_VOXEL_SIZE = 1.0

DEFAULT_CENTER_XY = True


DEFAULT_NORMALIZE_HEIGHT = True

DEFAULT_TARGET_HEIGHT = 2.0


DEFAULT_OBJECT_NAME = (
    "MeshvennSDF"
)

DEFAULT_MESH_NAME = (
    "MeshvennSDFMesh"
)


MINIMUM_PROJECTION_COUNT = 2


# =========================================================
# Configuration
# =========================================================

@dataclass(frozen=True)
class SDFReconstructionConfig:
    """
    Effective SDF Reconstruction V1 configuration.

    The first implementation deliberately uses the pure
    Python reference core.

    This gives us a correctness baseline before moving the
    expensive field construction / Surface Nets extraction
    to C++.

    Existing generic settings remain valid:

        resolution
        symmetry_x
        normalize_height
        target_height

    SDF-specific properties are read defensively when
    available:

        sdf_resolution
        sdf_symmetry_x
        sdf_voxel_size
        sdf_smoothness
        sdf_surface_offset
        sdf_iso_level
        sdf_gradient_step_scale

    This means the implementation can land before the UI
    properties without breaking older .blend files.
    """

    resolution: int = (
        DEFAULT_RESOLUTION
    )

    symmetry_x: bool = False

    voxel_size: float = (
        DEFAULT_VOXEL_SIZE
    )

    center_xy: bool = (
        DEFAULT_CENTER_XY
    )

    smoothness: float = (
        DEFAULT_SMOOTHNESS
    )

    surface_offset: float = (
        DEFAULT_SURFACE_OFFSET
    )

    iso_level: float = (
        DEFAULT_ISO_LEVEL
    )

    gradient_step_scale: float = (
        DEFAULT_GRADIENT_STEP_SCALE
    )

    normalize_height: bool = (
        DEFAULT_NORMALIZE_HEIGHT
    )

    target_height: float = (
        DEFAULT_TARGET_HEIGHT
    )

    max_reference_voxels: int = (
        DEFAULT_REFERENCE_MAX_VOXELS
    )

    def validate(
        self,
    ) -> None:
        if (
            not isinstance(
                self.resolution,
                int,
            )
            or isinstance(
                self.resolution,
                bool,
            )
            or self.resolution
            < MINIMUM_RESOLUTION
            or self.resolution
            > MAXIMUM_RESOLUTION
        ):
            raise ValueError(
                (
                    "SDF resolution must be "
                    f"between {MINIMUM_RESOLUTION} "
                    f"and {MAXIMUM_RESOLUTION}."
                )
            )

        if (
            not math.isfinite(
                float(
                    self.voxel_size
                )
            )
            or self.voxel_size <= 0.0
        ):
            raise ValueError(
                (
                    "SDF voxel size must be "
                    "finite and greater than zero."
                )
            )

        if (
            not math.isfinite(
                float(
                    self.smoothness
                )
            )
            or self.smoothness < 0.0
        ):
            raise ValueError(
                (
                    "SDF smoothness must be "
                    "finite and >= 0."
                )
            )

        if not math.isfinite(
            float(
                self.surface_offset
            )
        ):
            raise ValueError(
                (
                    "SDF surface offset "
                    "must be finite."
                )
            )

        if not math.isfinite(
            float(
                self.iso_level
            )
        ):
            raise ValueError(
                (
                    "SDF iso level "
                    "must be finite."
                )
            )

        if (
            not math.isfinite(
                float(
                    self.gradient_step_scale
                )
            )
            or self.gradient_step_scale
            <= 0.0
        ):
            raise ValueError(
                (
                    "SDF gradient step "
                    "must be finite and "
                    "greater than zero."
                )
            )

        if (
            not math.isfinite(
                float(
                    self.target_height
                )
            )
            or self.target_height <= 0.0
        ):
            raise ValueError(
                (
                    "Target height must be "
                    "finite and greater than zero."
                )
            )

        # -------------------------------------------------
        # Also validates the pure-Python reference memory /
        # sample-count guard.
        # -------------------------------------------------

        self.to_build_config().validate()

        self.to_surface_config().validate()

    @property
    def sample_count(
        self,
    ) -> int:
        return (
            self.resolution
            * self.resolution
            * self.resolution
        )

    @property
    def estimated_field_bytes(
        self,
    ) -> int:
        # Dense float32 SDF field only.
        return (
            self.sample_count
            * 4
        )

    @property
    def estimated_field_mib(
        self,
    ) -> float:
        return (
            float(
                self.estimated_field_bytes
            )
            / (
                1024.0
                * 1024.0
            )
        )

    def to_build_config(
        self,
    ) -> SDFBuildConfig:
        return SDFBuildConfig(
            width=(
                self.resolution
            ),

            depth=(
                self.resolution
            ),

            height=(
                self.resolution
            ),

            symmetry_x=(
                self.symmetry_x
            ),

            smoothness=(
                self.smoothness
            ),

            surface_offset=(
                self.surface_offset
            ),

            iso_level=(
                self.iso_level
            ),

            max_voxels=(
                self.max_reference_voxels
            ),
        )

    def to_surface_config(
        self,
    ) -> SDFSurfaceConfig:
        return SDFSurfaceConfig(
            iso_level=(
                self.iso_level
            ),

            gradient_step_scale=(
                self.gradient_step_scale
            ),

            generate_normals=True,
        )


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


# =========================================================
# Context / source
# =========================================================

def _resolve_settings(
    context: PipelineContext,
) -> Any:
    if context.settings is not None:
        return (
            context.settings
        )

    if context.scene is None:
        return None

    return getattr(
        context.scene,
        "bpt_settings",
        None,
    )


def _require_input_source(
    context: PipelineContext,
) -> Any:
    """
    SDF uses capabilities instead of depending on the
    concrete ProjectionImagesOutput class.

    Required source capability:

        source.views

    Required view capabilities:

        mask
        azimuth_degrees
        elevation_degrees

    Optional:

        flip_x
        name
    """

    source = (
        context.require_output(
            PipelineStage.INPUT
        )
    )

    views = getattr(
        source,
        "views",
        None,
    )

    if views is None:
        raise TypeError(
            (
                "INPUT output does not expose "
                "projection views required "
                "by SDF Reconstruction."
            )
        )

    return source


def _source_views(
    source: Any,
) -> tuple[
    Any,
    ...
]:
    views = getattr(
        source,
        "views",
        None,
    )

    if views is None:
        raise TypeError(
            (
                "INPUT source does not "
                "expose views."
            )
        )

    try:
        resolved = tuple(
            views
        )

    except TypeError as exc:
        raise TypeError(
            (
                "INPUT source views "
                "are not iterable."
            )
        ) from exc

    if len(
        resolved
    ) < MINIMUM_PROJECTION_COUNT:
        raise ValueError(
            (
                "SDF Reconstruction requires "
                "at least two projection views."
            )
        )

    for (
        index,
        view,
    ) in enumerate(
        resolved
    ):
        mask = getattr(
            view,
            "mask",
            None,
        )

        if not isinstance(
            mask,
            BinaryMask,
        ):
            raise TypeError(
                (
                    f"Projection {index} does not "
                    "expose a BinaryMask."
                )
            )

        try:
            float(
                getattr(
                    view,
                    "azimuth_degrees",
                )
            )

            float(
                getattr(
                    view,
                    "elevation_degrees",
                )
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
        ) as exc:
            raise TypeError(
                (
                    f"Projection {index} does not "
                    "expose valid camera angles."
                )
            ) from exc

    return resolved


def require_sdf_reconstruction_output(
    context: PipelineContext,
) -> SDFReconstructionOutput:
    output = (
        context.require_output(
            PipelineStage.GEOMETRY
        )
    )

    if not isinstance(
        output,
        SDFReconstructionOutput,
    ):
        raise TypeError(
            (
                "GEOMETRY output is incompatible "
                f'with "{IMPLEMENTATION_ID}". '
                "Expected SDFReconstructionOutput, "
                "received "
                f"{type(output).__name__}."
            )
        )

    return output


# =========================================================
# Settings resolution
# =========================================================

def _read_setting(
    settings: Any,
    name: str,
    default: Any,
) -> Any:
    if settings is None:
        return default

    return getattr(
        settings,
        name,
        default,
    )


def _legacy_geometry_setting(
    settings: Any,
    sdf_name: str,
    legacy_name: str,
    default: Any,
) -> Any:
    """
    Prefer the future SDF-specific property.

    Fall back to the existing Visual Hull geometry property
    so SDF V1 is immediately runnable before dedicated UI
    controls land.
    """

    if settings is None:
        return default

    if hasattr(
        settings,
        sdf_name,
    ):
        return getattr(
            settings,
            sdf_name,
        )

    return getattr(
        settings,
        legacy_name,
        default,
    )


def _config_from_settings(
    settings: Any,
) -> SDFReconstructionConfig:
    config = (
        SDFReconstructionConfig(
            resolution=int(
                _legacy_geometry_setting(
                    settings,
                    "sdf_resolution",
                    "resolution",
                    DEFAULT_RESOLUTION,
                )
            ),

            symmetry_x=bool(
                _legacy_geometry_setting(
                    settings,
                    "sdf_symmetry_x",
                    "symmetry_x",
                    False,
                )
            ),

            voxel_size=float(
                _legacy_geometry_setting(
                    settings,
                    "sdf_voxel_size",
                    "voxel_size",
                    DEFAULT_VOXEL_SIZE,
                )
            ),

            center_xy=bool(
                _read_setting(
                    settings,
                    "sdf_center_xy",
                    DEFAULT_CENTER_XY,
                )
            ),

            smoothness=float(
                _read_setting(
                    settings,
                    "sdf_smoothness",
                    DEFAULT_SMOOTHNESS,
                )
            ),

            surface_offset=float(
                _read_setting(
                    settings,
                    "sdf_surface_offset",
                    DEFAULT_SURFACE_OFFSET,
                )
            ),

            iso_level=float(
                _read_setting(
                    settings,
                    "sdf_iso_level",
                    DEFAULT_ISO_LEVEL,
                )
            ),

            gradient_step_scale=float(
                _read_setting(
                    settings,
                    "sdf_gradient_step_scale",
                    DEFAULT_GRADIENT_STEP_SCALE,
                )
            ),

            normalize_height=bool(
                _read_setting(
                    settings,
                    "normalize_height",
                    DEFAULT_NORMALIZE_HEIGHT,
                )
            ),

            target_height=float(
                _read_setting(
                    settings,
                    "target_height",
                    DEFAULT_TARGET_HEIGHT,
                )
            ),

            max_reference_voxels=(
                DEFAULT_REFERENCE_MAX_VOXELS
            ),
        )
    )

    config.validate()

    return config


# =========================================================
# Projection space
# =========================================================

def _projection_space_from_config(
    config: SDFReconstructionConfig,
) -> GeometryProjectionSpace:
    """
    MATERIAL currently expects the historical
    surface-envelope-v1 convention.

    SDF itself works in normalized [-1,+1] coordinates.

    We therefore expose an envelope whose inverse mapping
    reproduces exactly those normalized coordinates.
    """

    return GeometryProjectionSpace(
        width=(
            config.resolution
        ),

        depth=(
            config.resolution
        ),

        height=(
            config.resolution
        ),

        voxel_size=(
            config.voxel_size
        ),

        center_xy=(
            config.center_xy
        ),
    )


def _normalized_to_local(
    position: tuple[
        float,
        float,
        float,
    ],
    projection_space: GeometryProjectionSpace,
) -> tuple[
    float,
    float,
    float,
]:
    """
    Convert SDF normalized coordinates into the exact local
    surface-envelope convention consumed by MATERIAL.

    This is the inverse of:

        surface_position_to_normalized()

    for GeometryProjectionSpace.SURFACE_ENVELOPE_V1.
    """

    (
        nx,
        ny,
        nz,
    ) = position

    nx = float(
        nx
    )

    ny = float(
        ny
    )

    nz = float(
        nz
    )

    physical_width = (
        projection_space
        .physical_width
    )

    physical_depth = (
        projection_space
        .physical_depth
    )

    physical_height = (
        projection_space
        .physical_height
    )

    if projection_space.center_xy:
        x = (
            nx
            * physical_width
            * 0.5
        )

        y = (
            ny
            * physical_depth
            * 0.5
        )

    else:
        x = (
            (
                nx
                + 1.0
            )
            * physical_width
            * 0.5
        )

        y = (
            (
                ny
                + 1.0
            )
            * physical_depth
            * 0.5
        )

    z = (
        (
            nz
            + 1.0
        )
        * physical_height
        * 0.5
    )

    return (
        x,
        y,
        z,
    )


# =========================================================
# Blender mesh creation
# =========================================================

def _make_active(
    obj: bpy.types.Object,
) -> None:
    view_layer = (
        bpy.context.view_layer
    )

    if view_layer is None:
        return

    active = (
        view_layer.objects.active
    )

    if (
        active is not None
        and active != obj
    ):
        try:
            active.select_set(
                False
            )

        except Exception:
            pass

    obj.select_set(
        True
    )

    view_layer.objects.active = (
        obj
    )


def _shade_smooth(
    obj: bpy.types.Object,
) -> None:
    if obj.type != "MESH":
        raise TypeError(
            (
                "SDF surface object "
                "must be a mesh."
            )
        )

    polygon_count = len(
        obj.data.polygons
    )

    if polygon_count <= 0:
        return

    smooth_values = (
        array(
            "b",
            [
                1
            ],
        )
        * polygon_count
    )

    obj.data.polygons.foreach_set(
        "use_smooth",
        smooth_values,
    )

    obj.data.update()


def _create_blender_surface(
    surface_result: SDFSurfaceResult,
    projection_space: GeometryProjectionSpace,
    *,
    mesh_name: str = DEFAULT_MESH_NAME,
    object_name: str = DEFAULT_OBJECT_NAME,
) -> bpy.types.Object:
    """
    Inject the algorithm-neutral SDF surface into Blender.

    Crucially, we do NOT keep vertices in normalized
    [-1,+1] coordinates.

    MATERIAL expects mesh-local coordinates following
    GeometryProjectionSpace, so each normalized SDF vertex
    is converted to surface-envelope local space first.
    """

    surface = (
        surface_result.mesh
    )

    if surface.vertex_count <= 0:
        raise ValueError(
            (
                "SDF surface contains "
                "no vertices."
            )
        )

    if surface.polygon_count <= 0:
        raise ValueError(
            (
                "SDF surface contains "
                "no polygons."
            )
        )

    vertices = [
        _normalized_to_local(
            vertex.position,
            projection_space,
        )
        for vertex
        in surface.vertices
    ]

    faces = [
        tuple(
            int(
                index
            )
            for index
            in face
        )
        for face
        in surface.faces
    ]

    mesh = (
        bpy.data.meshes.new(
            mesh_name
        )
    )

    obj = None

    try:
        mesh.from_pydata(
            vertices,
            [],
            faces,
        )

        mesh.update(
            calc_edges=True
        )

        mesh.validate(
            verbose=False,
            clean_customdata=False,
        )

        if len(
            mesh.vertices
        ) <= 0:
            raise RuntimeError(
                (
                    "Blender SDF mesh contains "
                    "no vertices after injection."
                )
            )

        if len(
            mesh.polygons
        ) <= 0:
            raise RuntimeError(
                (
                    "Blender SDF mesh contains "
                    "no polygons after injection."
                )
            )

        obj = (
            bpy.data.objects.new(
                object_name,
                mesh,
            )
        )

        collection = (
            bpy.context.collection
            or bpy.context.scene.collection
        )

        collection.objects.link(
            obj
        )

        _shade_smooth(
            obj
        )

        _make_active(
            obj
        )

        return obj

    except Exception:
        if obj is not None:
            try:
                bpy.data.objects.remove(
                    obj,
                    do_unlink=True,
                )

            except Exception:
                pass

        if mesh.users == 0:
            try:
                bpy.data.meshes.remove(
                    mesh
                )

            except Exception:
                pass

        raise


def _remove_blender_object(
    obj: (
        bpy.types.Object
        | None
    ),
) -> None:
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


# =========================================================
# Height normalization
# =========================================================

def _apply_non_destructive_height_normalization(
    obj: bpy.types.Object,
    *,
    enabled: bool,
    target_height: float,
) -> float:
    """
    Apply target-height normalization through object.scale.

    Never mutate obj.data coordinates before MATERIAL.

    Projected Color and UV Bake must still be able to invert:

        local surface coordinate
            ↓
        GeometryProjectionSpace
            ↓
        normalized reconstruction coordinate
    """

    if not enabled:
        return 1.0

    if (
        not math.isfinite(
            float(
                target_height
            )
        )
        or target_height <= 0.0
    ):
        raise ValueError(
            (
                "Target height must be "
                "finite and greater than zero."
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
        float(
            target_height
        )
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
    source: Any,
    projection_space: GeometryProjectionSpace,
    sdf_result: SDFBuildResult,
    surface_result: SDFSurfaceResult,
    config: SDFReconstructionConfig,
    normalization_scale: float,
) -> None:
    sdf_stats = (
        sdf_result.stats
    )

    surface_stats = (
        surface_result.stats
    )

    # -----------------------------------------------------
    # Generic geometry metadata
    # -----------------------------------------------------

    obj[
        "meshvenn_geometry_implementation"
    ] = (
        IMPLEMENTATION_ID
    )

    obj[
        "meshvenn_geometry_version"
    ] = (
        IMPLEMENTATION_VERSION
    )

    obj[
        "meshvenn_geometry_backend"
    ] = (
        "python-reference"
    )

    obj[
        "meshvenn_projection_space_preserved"
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
    # SDF build
    # -----------------------------------------------------

    obj[
        "meshvenn_sdf_resolution"
    ] = (
        config.resolution
    )

    obj[
        "meshvenn_sdf_symmetry_x"
    ] = (
        config.symmetry_x
    )

    obj[
        "meshvenn_sdf_smoothness"
    ] = float(
        config.smoothness
    )

    obj[
        "meshvenn_sdf_surface_offset"
    ] = float(
        config.surface_offset
    )

    obj[
        "meshvenn_sdf_iso_level"
    ] = float(
        config.iso_level
    )

    obj[
        "meshvenn_sdf_sample_count"
    ] = (
        sdf_stats.voxel_count
    )

    obj[
        "meshvenn_sdf_projection_count"
    ] = (
        sdf_stats.projection_count
    )

    obj[
        "meshvenn_sdf_projection_samples"
    ] = (
        sdf_stats
        .projection_sample_count
    )

    obj[
        "meshvenn_sdf_min_distance"
    ] = float(
        sdf_stats
        .minimum_distance
    )

    obj[
        "meshvenn_sdf_max_distance"
    ] = float(
        sdf_stats
        .maximum_distance
    )

    obj[
        "meshvenn_sdf_inside_ratio"
    ] = float(
        sdf_stats
        .inside_ratio
    )

    # -----------------------------------------------------
    # Surface Nets
    # -----------------------------------------------------

    obj[
        "meshvenn_sdf_surface_active_cells"
    ] = (
        surface_stats
        .active_cells
    )

    obj[
        "meshvenn_sdf_surface_crossing_edges"
    ] = (
        surface_stats
        .crossing_grid_edges
    )

    obj[
        "meshvenn_sdf_surface_quads"
    ] = (
        surface_stats
        .emitted_quads
    )

    obj[
        "meshvenn_sdf_surface_boundary_skips"
    ] = (
        surface_stats
        .skipped_boundary_edges
    )

    obj[
        "meshvenn_sdf_surface_missing_cell_skips"
    ] = (
        surface_stats
        .skipped_missing_cell_edges
    )

    # -----------------------------------------------------
    # Historical BPT diagnostics
    #
    # Keep common diagnostic keys available while clearly
    # reporting a different engine.
    # -----------------------------------------------------

    obj[
        "bpt_engine"
    ] = (
        "python-sdf-reference"
    )

    obj[
        "bpt_mesh_mode"
    ] = (
        "sdf_surface_nets"
    )

    obj[
        "bpt_projection_count"
    ] = (
        sdf_stats.projection_count
    )

    obj[
        "bpt_resolution"
    ] = (
        config.resolution
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
# UI
# =========================================================

def _draw_optional_property(
    layout,
    settings,
    property_name: str,
    label: str,
) -> bool:
    if not hasattr(
        settings,
        property_name,
    ):
        return False

    layout.prop(
        settings,
        property_name,
        text=label,
    )

    return True


# =========================================================
# Implementation
# =========================================================

class SDFReconstructionImplementation:
    """
    Experimental GEOMETRY implementation.

        INPUT views
            ↓
        BinaryMask
            ↓
        exact 2D distance transform
            ↓
        multi-view SDF fusion
            ↓
        dense SDFVolume<float>
            ↓
        continuous Surface Nets
            ↓
        normalized SDFSurfaceMesh
            ↓
        surface-envelope local coordinates
            ↓
        Blender mesh
            ↓
        GeometrySurfaceOutput

    The current backend is deliberately pure Python.

    It establishes the semantic / visual reference before
    introducing native acceleration.
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
                "SDF Reconstruction V1"
            ),

            description=(
                "Reconstruct a continuous signed-distance "
                "field from silhouette projections and "
                "extract a sub-voxel Surface Nets mesh."
            ),

            version=(
                IMPLEMENTATION_VERSION
            ),

            experimental=True,

            supports_headless=True,

            capabilities=(
                "signed-distance-field",
                "silhouette-reconstruction",
                "continuous-surface",
                "surface-nets",
                "sub-voxel",
                "multi-view",
                "symmetry-x",
                "generic-geometry",
                "projection-space",
                "python-reference",
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
                _require_input_source(
                    context
                )
            )

            views = (
                _source_views(
                    source
                )
            )

        except Exception as exc:
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "Prepared silhouette input "
                        "is unavailable."
                    ),
                    details={
                        "error": str(
                            exc
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
                        "SDF Reconstruction "
                        "configuration is invalid."
                    ),
                    details={
                        "error": str(
                            exc
                        ),
                    },
                )
            )

        empty_mask_count = sum(
            1
            for view
            in views
            if (
                view.mask
                .occupied_count
                == 0
            )
        )

        details = {
            "backend": (
                "python-reference"
            ),

            "projection_count": len(
                views
            ),

            "resolution": (
                config.resolution
            ),

            "sample_count": (
                config.sample_count
            ),

            "estimated_field_mib": (
                config
                .estimated_field_mib
            ),

            "symmetry_x": (
                config.symmetry_x
            ),

            "smoothness": (
                config.smoothness
            ),

            "surface_offset": (
                config.surface_offset
            ),

            "iso_level": (
                config.iso_level
            ),

            "empty_masks": (
                empty_mask_count
            ),
        }

        reasons = [
            (
                "SDF V1 currently uses the "
                "pure-Python reference backend; "
                "native acceleration is pending."
            )
        ]

        if empty_mask_count > 0:
            reasons.append(
                (
                    f"{empty_mask_count} projection "
                    "mask"
                    + (
                        "s are"
                        if empty_mask_count != 1
                        else " is"
                    )
                    + " empty; the mathematical "
                    "intersection may be empty."
                )
            )

        return (
            ImplementationAvailability
            .degraded(
                " ".join(
                    reasons
                ),
                details=details,
            )
        )

    # -----------------------------------------------------
    # Settings UI
    # -----------------------------------------------------

    def draw_settings(
        self,
        layout,
        context,
    ) -> None:
        settings = getattr(
            context.scene,
            "bpt_settings",
            None,
        )

        if settings is None:
            return

        backend_box = (
            layout.box()
        )

        backend_box.label(
            text=(
                "SDF V1 — Python Reference"
            ),
            icon="EXPERIMENTAL",
        )

        backend_box.label(
            text=(
                "Continuous sub-voxel "
                "Surface Nets"
            ),
        )

        geometry_box = (
            layout.box()
        )

        geometry_box.label(
            text="Field",
            icon="MOD_VOLUME",
        )

        if not _draw_optional_property(
            geometry_box,
            settings,
            "sdf_resolution",
            "Resolution",
        ):
            _draw_optional_property(
                geometry_box,
                settings,
                "resolution",
                "Resolution",
            )

        if not _draw_optional_property(
            geometry_box,
            settings,
            "sdf_symmetry_x",
            "Symmetry X",
        ):
            _draw_optional_property(
                geometry_box,
                settings,
                "symmetry_x",
                "Symmetry X",
            )

        _draw_optional_property(
            geometry_box,
            settings,
            "sdf_smoothness",
            "Constraint Smoothness",
        )

        _draw_optional_property(
            geometry_box,
            settings,
            "sdf_surface_offset",
            "Surface Offset",
        )

        _draw_optional_property(
            geometry_box,
            settings,
            "sdf_iso_level",
            "Iso Level",
        )

        output_box = (
            layout.box()
        )

        output_box.label(
            text="Output",
            icon="MESH_DATA",
        )

        _draw_optional_property(
            output_box,
            settings,
            "normalize_height",
            "Normalize Height",
        )

        if bool(
            getattr(
                settings,
                "normalize_height",
                DEFAULT_NORMALIZE_HEIGHT,
            )
        ):
            _draw_optional_property(
                output_box,
                settings,
                "target_height",
                "Target Height",
            )

        try:
            config = (
                _config_from_settings(
                    settings
                )
            )

            backend_box.label(
                text=(
                    f"{config.sample_count:,} "
                    "SDF samples"
                ),
                icon="INFO",
            )

            backend_box.label(
                text=(
                    f"Dense field ≈ "
                    f"{config.estimated_field_mib:.1f} MiB"
                ),
            )

        except Exception:
            pass

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
                _require_input_source(
                    context
                )
            )

            views = (
                _source_views(
                    source
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
                        "Prepared silhouette input "
                        f"is unavailable: {exc}"
                    ),
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
                        "Invalid SDF Reconstruction "
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

        window_manager = getattr(
            bpy.context,
            "window_manager",
            None,
        )

        progress_active = False

        try:
            if window_manager is not None:
                try:
                    window_manager.progress_begin(
                        0,
                        (
                            config.resolution
                            + 4
                        ),
                    )

                    progress_active = True

                except Exception:
                    window_manager = None

            # -------------------------------------------------
            # 1. Build continuous SDF
            # -------------------------------------------------

            def sdf_progress(
                progress: SDFBuildProgress,
            ) -> None:
                if window_manager is None:
                    return

                try:
                    window_manager.progress_update(
                        progress
                        .completed_slices
                    )

                except Exception:
                    pass

            try:
                sdf_result = (
                    build_sdf_from_views(
                        views,

                        config=(
                            config
                            .to_build_config()
                        ),

                        progress_callback=(
                            sdf_progress
                        ),
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
                            "SDF field construction "
                            f"failed: {exc}"
                        ),

                        metadata={
                            "resolution": (
                                config.resolution
                            ),

                            "projection_count": len(
                                views
                            ),

                            "backend": (
                                "python-reference"
                            ),
                        },
                    )
                )

            if window_manager is not None:
                try:
                    window_manager.progress_update(
                        config.resolution
                        + 1
                    )

                except Exception:
                    pass

            # -------------------------------------------------
            # Field must contain both sides of the iso-surface.
            # -------------------------------------------------

            if not (
                sdf_result
                .volume
                .crosses_surface
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
                            "SDF field does not cross "
                            "the requested iso-surface."
                        ),

                        metadata={
                            "minimum_distance": (
                                sdf_result
                                .volume
                                .minimum_value
                            ),

                            "maximum_distance": (
                                sdf_result
                                .volume
                                .maximum_value
                            ),

                            "iso_level": (
                                config.iso_level
                            ),

                            "inside_ratio": (
                                sdf_result
                                .stats
                                .inside_ratio
                            ),
                        },
                    )
                )

            # -------------------------------------------------
            # 2. Continuous Surface Nets
            # -------------------------------------------------

            try:
                surface_result = (
                    extract_surface_nets(
                        sdf_result.volume,

                        config=(
                            config
                            .to_surface_config()
                        ),
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
                            "SDF Surface Nets "
                            f"extraction failed: {exc}"
                        ),
                    )
                )

            surface = (
                surface_result.mesh
            )

            if (
                surface.vertex_count <= 0
                or surface.polygon_count <= 0
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
                            "SDF extraction produced "
                            "an empty surface mesh."
                        ),

                        metadata={
                            "active_cells": (
                                surface_result
                                .stats
                                .active_cells
                            ),

                            "crossing_edges": (
                                surface_result
                                .stats
                                .crossing_grid_edges
                            ),

                            "boundary_skips": (
                                surface_result
                                .stats
                                .skipped_boundary_edges
                            ),
                        },
                    )
                )

            if window_manager is not None:
                try:
                    window_manager.progress_update(
                        config.resolution
                        + 2
                    )

                except Exception:
                    pass

            # -------------------------------------------------
            # 3. Generic projection coordinate space
            # -------------------------------------------------

            projection_space = (
                _projection_space_from_config(
                    config
                )
            )

            # -------------------------------------------------
            # 4. Blender mesh
            # -------------------------------------------------

            obj = (
                _create_blender_surface(
                    surface_result,
                    projection_space,
                )
            )

            if window_manager is not None:
                try:
                    window_manager.progress_update(
                        config.resolution
                        + 3
                    )

                except Exception:
                    pass

            # -------------------------------------------------
            # 5. Non-destructive output normalization
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
            # 6. Metadata
            # -------------------------------------------------

            _write_geometry_metadata(
                obj,

                source=source,

                projection_space=(
                    projection_space
                ),

                sdf_result=(
                    sdf_result
                ),

                surface_result=(
                    surface_result
                ),

                config=config,

                normalization_scale=(
                    normalization_scale
                ),
            )

            # -------------------------------------------------
            # 7. Generic GEOMETRY output
            # -------------------------------------------------

            output_metrics = {
                "projection_count": (
                    sdf_result
                    .stats
                    .projection_count
                ),

                "resolution": (
                    config.resolution
                ),

                "sample_count": (
                    sdf_result
                    .stats
                    .voxel_count
                ),

                "projection_sample_count": (
                    sdf_result
                    .stats
                    .projection_sample_count
                ),

                "inside_ratio": (
                    sdf_result
                    .stats
                    .inside_ratio
                ),

                "minimum_distance": (
                    sdf_result
                    .stats
                    .minimum_distance
                ),

                "maximum_distance": (
                    sdf_result
                    .stats
                    .maximum_distance
                ),

                "active_cells": (
                    surface_result
                    .stats
                    .active_cells
                ),

                "crossing_grid_edges": (
                    surface_result
                    .stats
                    .crossing_grid_edges
                ),

                "vertex_count": (
                    surface
                    .vertex_count
                ),

                "polygon_count": (
                    surface
                    .polygon_count
                ),

                "quad_count": (
                    surface
                    .quad_count
                ),

                "triangle_count": (
                    surface
                    .triangle_count
                ),

                "normalization_scale": (
                    normalization_scale
                ),
            }

            output_metadata = {
                "backend": (
                    "python-reference"
                ),

                "field": (
                    "signed-distance"
                ),

                "surface_extractor": (
                    "surface-nets"
                ),

                "sub_voxel": True,

                "symmetry_x": (
                    config.symmetry_x
                ),

                "smoothness": (
                    config.smoothness
                ),

                "surface_offset": (
                    config.surface_offset
                ),

                "iso_level": (
                    config.iso_level
                ),

                "projection_convention": (
                    projection_space
                    .convention
                    .value
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

                "projection_space_local_coordinates_preserved": (
                    True
                ),
            }

            output = (
                SDFReconstructionOutput(
                    blender_object=obj,

                    source=source,

                    projection_space=(
                        projection_space
                    ),

                    sdf_result=(
                        sdf_result
                    ),

                    surface_result=(
                        surface_result
                    ),

                    config=config,

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
            # Global pipeline diagnostics
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
                "geometry_backend"
            ] = (
                "python-reference"
            )

            context.metadata[
                "geometry_mesh_mode"
            ] = (
                "sdf_surface_nets"
            )

            context.metadata[
                "geometry_sdf_resolution"
            ] = (
                config.resolution
            )

            context.metadata[
                "geometry_sdf_inside_ratio"
            ] = (
                sdf_result
                .stats
                .inside_ratio
            )

            context.metadata[
                "geometry_sdf_active_cells"
            ] = (
                surface_result
                .stats
                .active_cells
            )

            context.metadata[
                "geometry_projection_space"
            ] = {
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
            }

            if window_manager is not None:
                try:
                    window_manager.progress_update(
                        config.resolution
                        + 4
                    )

                except Exception:
                    pass

            # -------------------------------------------------
            # Success
            # -------------------------------------------------

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
                        "SDF reconstruction generated: "
                        f"{sdf_result.stats.voxel_count} "
                        "field samples, "
                        f"{surface.vertex_count} vertices, "
                        f"{surface.polygon_count} quads."
                    ),

                    metrics=(
                        output_metrics
                    ),

                    metadata={
                        "object_name": (
                            obj.name
                        ),

                        "mesh_name": (
                            obj
                            .data
                            .name
                        ),

                        "backend": (
                            "python-reference"
                        ),

                        "resolution": (
                            config.resolution
                        ),

                        "projection_count": (
                            sdf_result
                            .stats
                            .projection_count
                        ),

                        "symmetry_x": (
                            config.symmetry_x
                        ),

                        "smoothness": (
                            config.smoothness
                        ),

                        "surface_offset": (
                            config.surface_offset
                        ),

                        "iso_level": (
                            config.iso_level
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

                        "surface": {
                            "active_cells": (
                                surface_result
                                .stats
                                .active_cells
                            ),

                            "crossing_edges": (
                                surface_result
                                .stats
                                .crossing_grid_edges
                            ),

                            "boundary_skips": (
                                surface_result
                                .stats
                                .skipped_boundary_edges
                            ),

                            "missing_cell_skips": (
                                surface_result
                                .stats
                                .skipped_missing_cell_edges
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

                        "projection_space_local_coordinates_preserved": (
                            True
                        ),
                    },
                )
            )

        except Exception:
            # -------------------------------------------------
            # Any Blender object created by a failed GEOMETRY
            # stage must not leak into the scene.
            # -------------------------------------------------

            _remove_blender_object(
                obj
            )

            raise

        finally:
            if (
                progress_active
                and window_manager
                is not None
            ):
                try:
                    window_manager.progress_end()

                except Exception:
                    pass


# =========================================================
# Public API
# =========================================================

__all__ = (
    "DEFAULT_CENTER_XY",
    "DEFAULT_NORMALIZE_HEIGHT",
    "DEFAULT_OBJECT_NAME",
    "DEFAULT_RESOLUTION",
    "DEFAULT_TARGET_HEIGHT",
    "DEFAULT_VOXEL_SIZE",
    "IMPLEMENTATION_ID",
    "IMPLEMENTATION_VERSION",
    "MAXIMUM_RESOLUTION",
    "MINIMUM_PROJECTION_COUNT",
    "MINIMUM_RESOLUTION",
    "SDFReconstructionConfig",
    "SDFReconstructionImplementation",
    "SDFReconstructionOutput",
    "require_sdf_reconstruction_output",
)