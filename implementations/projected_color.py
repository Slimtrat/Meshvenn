from __future__ import annotations

import math

from dataclasses import dataclass
from typing import (
    Any,
    Sequence,
)

import bpy

from ..core.geometry_contracts import (
    GeometrySurfaceOutput,
    require_geometry_surface_output,
)
from ..core.material_blend import (
    MaterialBlendConfig,
)
from ..core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..core.projected_material import (
    BLEND_MODE,
    COLOR_ATTRIBUTE_NAME,
    MATERIAL_MODE,
    VISIBILITY_MODE,
    MaterialProjectionStats,
    apply_projected_material,
)


# =========================================================
# Constants
# =========================================================

IMPLEMENTATION_ID = (
    "projected-color-v1.2"
)

DEFAULT_ENABLE_VISIBILITY = True

DEFAULT_ALLOW_BACKFACE_FALLBACK = True

DEFAULT_FACING_POWER = 2.0

DEFAULT_MIN_FACING = 0.10

DEFAULT_RELATIVE_SCORE_CUTOFF = 0.20

DEFAULT_MAX_CONTRIBUTORS = 3

DEFAULT_WEIGHT_POWER = 1.5


# =========================================================
# Configuration
# =========================================================

@dataclass(frozen=True)
class ProjectedColorConfig:
    """
    Effective configuration of the built-in projected-color
    implementation.

    These defaults correspond to Material V1.2.

    They deliberately live at the implementation boundary,
    not in the generic pipeline core.
    """

    enable_visibility: bool = (
        DEFAULT_ENABLE_VISIBILITY
    )

    allow_backface_fallback: bool = (
        DEFAULT_ALLOW_BACKFACE_FALLBACK
    )

    facing_power: float = (
        DEFAULT_FACING_POWER
    )

    min_facing: float = (
        DEFAULT_MIN_FACING
    )

    relative_score_cutoff: float = (
        DEFAULT_RELATIVE_SCORE_CUTOFF
    )

    max_contributors: int = (
        DEFAULT_MAX_CONTRIBUTORS
    )

    weight_power: float = (
        DEFAULT_WEIGHT_POWER
    )

    def validate(
        self,
    ) -> None:
        if (
            not math.isfinite(
                self.facing_power
            )
            or self.facing_power < 0.0
        ):
            raise ValueError(
                (
                    "Facing power must be finite "
                    "and >= 0."
                )
            )

        blend_config = (
            self.to_blend_config()
        )

        blend_config.validate()

    def to_blend_config(
        self,
    ) -> MaterialBlendConfig:
        return (
            MaterialBlendConfig(
                min_facing=(
                    self.min_facing
                ),
                facing_power=(
                    self.facing_power
                ),
                relative_score_cutoff=(
                    self
                    .relative_score_cutoff
                ),
                max_contributors=(
                    self.max_contributors
                ),
                weight_power=(
                    self.weight_power
                ),
            )
        )


# =========================================================
# Material output
# =========================================================

@dataclass(frozen=True)
class ProjectedColorOutput:
    """
    Output contract of projected-color-v1.2.

    The Blender object is the SAME surface object produced
    by the GEOMETRY stage.

        any GeometrySurfaceOutput
                 ↓
        Projected Color V1.2
                 ↓
        same Blender object
        + CORNER color attribute

    This output is intentionally geometry-implementation
    agnostic.

    geometry may therefore originate from:

        Native Visual Hull
        SDF Reconstruction
        imported surface
        future reconstruction engine
    """

    blender_object: bpy.types.Object

    geometry: GeometrySurfaceOutput

    stats: MaterialProjectionStats

    config: ProjectedColorConfig

    material_mode: str

    visibility_mode: str

    blend_mode: str

    color_attribute: str

    @property
    def projected_vertices(
        self,
    ) -> int:
        return (
            self.stats
            .projected_vertices
        )

    @property
    def fallback_vertices(
        self,
    ) -> int:
        return (
            self.stats
            .fallback_vertices
        )

    @property
    def selected_samples(
        self,
    ) -> int:
        return (
            self.stats
            .selected_samples
        )

    @property
    def visible_samples(
        self,
    ) -> int:
        return (
            self.stats
            .visible_samples
        )

    @property
    def occluded_samples(
        self,
    ) -> int:
        return (
            self.stats
            .occluded_samples
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


def require_projected_color_output(
    context: PipelineContext,
) -> ProjectedColorOutput:
    """
    Typed accessor for EXPORT, diagnostics and future
    post-processing implementations.
    """

    output = (
        context.require_output(
            PipelineStage.MATERIAL
        )
    )

    if not isinstance(
        output,
        ProjectedColorOutput,
    ):
        raise TypeError(
            (
                "MATERIAL output is incompatible with "
                f'"{IMPLEMENTATION_ID}". Expected '
                "ProjectedColorOutput, received "
                f"{type(output).__name__}."
            )
        )

    return output


# =========================================================
# Configuration resolution
# =========================================================

def _read_setting(
    settings: Any,
    name: str,
    default: Any,
) -> Any:
    """
    Read an optional implementation-specific setting.

    The settings object may be:

        Blender BPT_PG_Settings
        SimpleNamespace from diagnostic scripts
        future implementation-specific settings adapter
    """

    if settings is None:
        return default

    return getattr(
        settings,
        name,
        default,
    )


def _config_from_settings(
    settings: Any,
) -> ProjectedColorConfig:
    config = (
        ProjectedColorConfig(
            enable_visibility=bool(
                _read_setting(
                    settings,
                    "material_enable_visibility",
                    DEFAULT_ENABLE_VISIBILITY,
                )
            ),

            allow_backface_fallback=bool(
                _read_setting(
                    settings,
                    "material_allow_backface_fallback",
                    DEFAULT_ALLOW_BACKFACE_FALLBACK,
                )
            ),

            facing_power=float(
                _read_setting(
                    settings,
                    "material_facing_power",
                    DEFAULT_FACING_POWER,
                )
            ),

            min_facing=float(
                _read_setting(
                    settings,
                    "material_min_facing",
                    DEFAULT_MIN_FACING,
                )
            ),

            relative_score_cutoff=float(
                _read_setting(
                    settings,
                    "material_relative_score_cutoff",
                    DEFAULT_RELATIVE_SCORE_CUTOFF,
                )
            ),

            max_contributors=int(
                _read_setting(
                    settings,
                    "material_max_contributors",
                    DEFAULT_MAX_CONTRIBUTORS,
                )
            ),

            weight_power=float(
                _read_setting(
                    settings,
                    "material_weight_power",
                    DEFAULT_WEIGHT_POWER,
                )
            ),
        )
    )

    config.validate()

    return config


# =========================================================
# Source material-view capability
# =========================================================

def _material_views_from_geometry(
    geometry: GeometrySurfaceOutput,
) -> tuple[
    Any,
    ...
]:
    """
    Resolve projection-material views from the INPUT source
    without requiring ProjectionImagesOutput.

    This is intentionally capability-based.

    Projected Color needs:

        geometry.source.material_views

    It does NOT need to know the concrete INPUT or GEOMETRY
    class which supplied them.

    A future input implementation can therefore participate
    simply by exposing a compatible material_views sequence.
    """

    source = (
        geometry.source
    )

    material_views = getattr(
        source,
        "material_views",
        None,
    )

    if material_views is None:
        raise TypeError(
            (
                "GEOMETRY source does not expose "
                "material_views required by "
                "Projected Color."
            )
        )

    try:
        resolved = tuple(
            material_views
        )

    except TypeError as exc:
        raise TypeError(
            (
                "GEOMETRY source material_views "
                "is not iterable."
            )
        ) from exc

    if not resolved:
        raise ValueError(
            (
                "No material projection views "
                "are available."
            )
        )

    return resolved


# =========================================================
# Geometry validation
# =========================================================

def _validate_geometry(
    geometry: GeometrySurfaceOutput,
) -> None:
    """
    Validate only the generic surface requirements needed by
    Projected Color.

    There must be no knowledge of:

        NativeVolume
        NativeMesh
        Visual Hull
        SDF internals
    """

    obj = (
        geometry.blender_object
    )

    if obj is None:
        raise ValueError(
            (
                "Geometry has no "
                "Blender object."
            )
        )

    if (
        getattr(
            obj,
            "type",
            None,
        )
        != "MESH"
    ):
        raise TypeError(
            (
                "Projected Color requires "
                "a mesh object."
            )
        )

    mesh = getattr(
        obj,
        "data",
        None,
    )

    if mesh is None:
        raise ValueError(
            (
                "Geometry object has "
                "no mesh data."
            )
        )

    if len(
        mesh.vertices
    ) == 0:
        raise ValueError(
            (
                "Geometry mesh contains "
                "no vertices."
            )
        )

    if len(
        mesh.polygons
    ) == 0:
        raise ValueError(
            (
                "Geometry mesh contains "
                "no polygons."
            )
        )

    if len(
        mesh.loops
    ) == 0:
        raise ValueError(
            (
                "Geometry mesh contains "
                "no loops."
            )
        )

    # -----------------------------------------------------
    # Projection-space validation.
    #
    # require_geometry_surface_output() already validates
    # the generic contract, but keeping this explicit here
    # makes errors produced by this implementation easier
    # to diagnose.
    # -----------------------------------------------------

    projection_space = (
        geometry.projection_space
    )

    if (
        projection_space.width <= 0
        or projection_space.depth <= 0
        or projection_space.height <= 0
    ):
        raise ValueError(
            (
                "Geometry contains invalid "
                "projection-space dimensions."
            )
        )

    if (
        not math.isfinite(
            projection_space
            .voxel_size
        )
        or projection_space
        .voxel_size
        <= 0.0
    ):
        raise ValueError(
            (
                "Geometry contains an invalid "
                "projection-space voxel size."
            )
        )

    # Validate that the convention is supported by the
    # current projection stack.

    projection_space.as_projection_kwargs()

    # Validate source capability as part of the complete
    # Projected Color compatibility check.

    _material_views_from_geometry(
        geometry
    )


# =========================================================
# Metadata
# =========================================================

def _write_material_metadata(
    obj: bpy.types.Object,
    *,
    output: ProjectedColorOutput,
) -> None:
    """
    Add generic Meshvenn metadata.

    apply_projected_material() already writes detailed BPT
    material / visibility / blend statistics.
    """

    obj[
        "meshvenn_material_implementation"
    ] = (
        IMPLEMENTATION_ID
    )

    obj[
        "meshvenn_material_version"
    ] = "1.2"

    obj[
        "meshvenn_material_mode"
    ] = (
        output.material_mode
    )

    obj[
        "meshvenn_material_visibility_mode"
    ] = (
        output.visibility_mode
    )

    obj[
        "meshvenn_material_blend_mode"
    ] = (
        output.blend_mode
    )

    obj[
        "meshvenn_material_color_attribute"
    ] = (
        output.color_attribute
    )

    obj[
        "meshvenn_material_geometry_implementation"
    ] = (
        output
        .geometry
        .implementation_id
    )

    obj[
        "meshvenn_material_projection_convention"
    ] = (
        output
        .geometry
        .projection_space
        .convention
        .value
    )


# =========================================================
# Statistics
# =========================================================

def _stats_metrics(
    stats: MaterialProjectionStats,
) -> dict[
    str,
    int,
]:
    """
    Standard metrics exposed to PipelineRunner/UI.

    Keep this explicit rather than serializing the dataclass
    wholesale so the public diagnostics contract is clear.
    """

    return {
        "vertices": (
            stats.vertex_count
        ),

        "loops": (
            stats.loop_count
        ),

        "views": (
            stats.view_count
        ),

        "projected_vertices": (
            stats.projected_vertices
        ),

        "fallback_vertices": (
            stats.fallback_vertices
        ),

        "projected_fallback_vertices": (
            stats
            .projected_fallback_vertices
        ),

        "neutral_fallback_vertices": (
            stats
            .neutral_fallback_vertices
        ),

        "candidate_samples": (
            stats.candidate_samples
        ),

        "source_rejected_samples": (
            stats
            .source_rejected_samples
        ),

        "visible_samples": (
            stats.visible_samples
        ),

        "occluded_samples": (
            stats.occluded_samples
        ),

        "front_facing_samples": (
            stats.front_facing_samples
        ),

        "backface_samples": (
            stats.backface_samples
        ),

        "grazing_rejected_samples": (
            stats
            .grazing_rejected_samples
        ),

        "relative_rejected_samples": (
            stats
            .relative_rejected_samples
        ),

        "top_k_rejected_samples": (
            stats
            .top_k_rejected_samples
        ),

        "selected_samples": (
            stats.selected_samples
        ),

        "accepted_samples": (
            stats.accepted_samples
        ),

        "rejected_samples": (
            stats.rejected_samples
        ),
    }


# =========================================================
# Implementation
# =========================================================

class ProjectedColorImplementation:
    """
    Built-in MATERIAL implementation.

        GeometrySurfaceOutput
                ↓
        source.material_views
                ↓
        GeometryProjectionSpace
                ↓
        V1.1 visibility
                ↓
        V1.2 adaptive blend
                ↓
        Blender CORNER color attribute
                ↓
        ProjectedColorOutput

    The implementation does not know whether the surface was
    created by:

        Native Visual Hull
        SDF Reconstruction
        another future geometry engine

    The actual projection/blending algorithm remains in
    core/projected_material.py.
    """

    _descriptor = (
        ImplementationDescriptor(
            identifier=(
                IMPLEMENTATION_ID
            ),

            stage=(
                PipelineStage.MATERIAL
            ),

            label=(
                "Projected Color V1.2"
            ),

            description=(
                "Project source images onto the generated "
                "mesh using visibility-aware adaptive "
                "multi-view blending."
            ),

            version="1.2",

            experimental=False,

            supports_headless=True,

            capabilities=(
                "projected-color",
                "vertex-color",
                "multi-view",
                "visibility-raycast",
                "adaptive-blend",
                "top-k",
                "grazing-rejection",
                "generic-geometry",
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
        try:
            geometry = (
                require_geometry_surface_output(
                    context
                )
            )

        except Exception as exc:
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "Compatible GEOMETRY surface "
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
            _validate_geometry(
                geometry
            )

            material_views = (
                _material_views_from_geometry(
                    geometry
                )
            )

        except Exception as exc:
            return (
                ImplementationAvailability
                .unavailable(
                    (
                        "Geometry is incompatible "
                        "with Projected Color."
                    ),
                    details={
                        "geometry_implementation": (
                            geometry
                            .implementation_id
                        ),

                        "error": str(
                            exc
                        ),
                    },
                )
            )

        settings = (
            _resolve_settings(
                context
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
                        "Projected Color "
                        "configuration is invalid."
                    ),
                    details={
                        "error": str(
                            exc
                        ),
                    },
                )
            )

        projection_space = (
            geometry
            .projection_space
        )

        return (
            ImplementationAvailability
            .ready_state(
                details={
                    "object": (
                        geometry
                        .object_name
                    ),

                    "geometry_implementation": (
                        geometry
                        .implementation_id
                    ),

                    "views": len(
                        material_views
                    ),

                    "material_mode": (
                        MATERIAL_MODE
                    ),

                    "visibility_mode": (
                        VISIBILITY_MODE
                        if (
                            config
                            .enable_visibility
                        )
                        else "disabled"
                    ),

                    "blend_mode": (
                        BLEND_MODE
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
                }
            )
        )

    # -----------------------------------------------------
    # Execute
    # -----------------------------------------------------

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        # -------------------------------------------------
        # Generic GEOMETRY contract.
        #
        # There must be no NativeVisualHullOutput dependency
        # below this point.
        # -------------------------------------------------

        try:
            geometry = (
                require_geometry_surface_output(
                    context
                )
            )

        except Exception as exc:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.MATERIAL
                    ),

                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),

                    message=(
                        "Compatible GEOMETRY surface "
                        f"is unavailable: {exc}"
                    ),
                )
            )

        try:
            _validate_geometry(
                geometry
            )

            material_views = list(
                _material_views_from_geometry(
                    geometry
                )
            )

        except Exception as exc:
            return (
                StageExecutionResult
                .failed_result(
                    stage=(
                        PipelineStage.MATERIAL
                    ),

                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),

                    message=(
                        "Geometry is incompatible with "
                        f"Projected Color: {exc}"
                    ),

                    metadata={
                        "geometry_implementation": (
                            geometry
                            .implementation_id
                        ),
                    },
                )
            )

        settings = (
            _resolve_settings(
                context
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
                        PipelineStage.MATERIAL
                    ),

                    implementation_id=(
                        IMPLEMENTATION_ID
                    ),

                    message=(
                        "Invalid Projected Color "
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

        obj = (
            geometry
            .blender_object
        )

        projection_space = (
            geometry
            .projection_space
        )

        blend_config = (
            config
            .to_blend_config()
        )

        # -------------------------------------------------
        # Projection
        #
        # IMPORTANT:
        #
        # GEOMETRY may normalize the visible object via
        # object-level scale.
        #
        # obj.data vertex coordinates MUST remain in the
        # GeometryProjectionSpace declared by GEOMETRY.
        #
        # This rule now applies identically to Visual Hull,
        # SDF and future reconstruction implementations.
        #
        # Do not apply transforms before this projection.
        # -------------------------------------------------

        stats = (
            apply_projected_material(
                obj,
                material_views,

                volume_width=(
                    projection_space
                    .width
                ),

                volume_depth=(
                    projection_space
                    .depth
                ),

                volume_height=(
                    projection_space
                    .height
                ),

                voxel_size=(
                    projection_space
                    .voxel_size
                ),

                center_xy=(
                    projection_space
                    .center_xy
                ),

                attribute_name=(
                    COLOR_ATTRIBUTE_NAME
                ),

                facing_power=(
                    config
                    .facing_power
                ),

                allow_backface_fallback=(
                    config
                    .allow_backface_fallback
                ),

                enable_visibility=(
                    config
                    .enable_visibility
                ),

                blend_config=(
                    blend_config
                ),
            )
        )

        effective_visibility_mode = (
            VISIBILITY_MODE
            if config.enable_visibility
            else "disabled"
        )

        output = (
            ProjectedColorOutput(
                blender_object=obj,

                geometry=geometry,

                stats=stats,

                config=config,

                material_mode=(
                    MATERIAL_MODE
                ),

                visibility_mode=(
                    effective_visibility_mode
                ),

                blend_mode=(
                    BLEND_MODE
                ),

                color_attribute=(
                    COLOR_ATTRIBUTE_NAME
                ),
            )
        )

        _write_material_metadata(
            obj,
            output=output,
        )

        # -------------------------------------------------
        # Pipeline diagnostics
        # -------------------------------------------------

        context.metadata[
            "material_object_name"
        ] = (
            obj.name
        )

        context.metadata[
            "material_mode"
        ] = (
            MATERIAL_MODE
        )

        context.metadata[
            "material_visibility_mode"
        ] = (
            effective_visibility_mode
        )

        context.metadata[
            "material_blend_mode"
        ] = (
            BLEND_MODE
        )

        context.metadata[
            "material_geometry_implementation"
        ] = (
            geometry
            .implementation_id
        )

        context.metadata[
            "material_projection_convention"
        ] = (
            projection_space
            .convention
            .value
        )

        context.metadata[
            "material_selected_samples"
        ] = (
            stats.selected_samples
        )

        context.metadata[
            "material_fallback_vertices"
        ] = (
            stats.fallback_vertices
        )

        # -------------------------------------------------
        # Result
        # -------------------------------------------------

        return (
            StageExecutionResult
            .succeeded(
                stage=(
                    PipelineStage.MATERIAL
                ),

                implementation_id=(
                    IMPLEMENTATION_ID
                ),

                payload=output,

                message=(
                    "Projected material generated: "
                    f"{stats.projected_vertices} direct "
                    "vertices, "
                    f"{stats.fallback_vertices} fallback "
                    "vertices, "
                    f"{stats.selected_samples} selected "
                    "samples."
                ),

                metrics=(
                    _stats_metrics(
                        stats
                    )
                ),

                metadata={
                    "object_name": (
                        obj.name
                    ),

                    "geometry_implementation": (
                        geometry
                        .implementation_id
                    ),

                    "material_mode": (
                        MATERIAL_MODE
                    ),

                    "visibility_mode": (
                        effective_visibility_mode
                    ),

                    "blend_mode": (
                        BLEND_MODE
                    ),

                    "color_attribute": (
                        COLOR_ATTRIBUTE_NAME
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

                    "configuration": {
                        "enable_visibility": (
                            config
                            .enable_visibility
                        ),

                        "allow_backface_fallback": (
                            config
                            .allow_backface_fallback
                        ),

                        "min_facing": (
                            config
                            .min_facing
                        ),

                        "facing_power": (
                            config
                            .facing_power
                        ),

                        "relative_score_cutoff": (
                            config
                            .relative_score_cutoff
                        ),

                        "max_contributors": (
                            config
                            .max_contributors
                        ),

                        "weight_power": (
                            config
                            .weight_power
                        ),
                    },
                },
            )
        )