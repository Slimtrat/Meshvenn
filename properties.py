from __future__ import annotations

import math

import bpy

from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from .core.pipeline_contracts import (
    PipelinePlan,
    PipelineStage,
    PipelineStageSelection,
)


# ---------------------------------------------------------
# Stable implementation defaults
#
# These are Blender-side defaults only.
#
# Concrete implementations will later register themselves
# under these stable ids through pipeline_registry.py.
# ---------------------------------------------------------

DEFAULT_INPUT_IMPLEMENTATION_ID = (
    "projection-images"
)

DEFAULT_GEOMETRY_IMPLEMENTATION_ID = (
    "native-visual-hull"
)

DEFAULT_MATERIAL_IMPLEMENTATION_ID = (
    "projected-color-v1.2"
)

DEFAULT_RIG_IMPLEMENTATION_ID = ""

DEFAULT_EXPORT_IMPLEMENTATION_ID = ""


# ---------------------------------------------------------
# Projection view
# ---------------------------------------------------------

class BPT_PG_ProjectionView(
    PropertyGroup
):
    name: StringProperty(
        name="Name",
        description="Projection label",
        default="Projection",
    )

    enabled: BoolProperty(
        name="Enabled",
        description=(
            "Use this projection during generation"
        ),
        default=True,
    )

    image: PointerProperty(
        name="Image",
        description=(
            "Silhouette image for this projection"
        ),
        type=bpy.types.Image,
    )

    azimuth: FloatProperty(
        name="Azimuth",
        description=(
            "Rotation around the vertical axis"
        ),
        default=0.0,
        min=-math.tau,
        max=math.tau,
        subtype="ANGLE",
        unit="ROTATION",
    )

    elevation: FloatProperty(
        name="Elevation",
        description="Vertical camera angle",
        default=0.0,
        min=-math.pi / 2.0,
        max=math.pi / 2.0,
        subtype="ANGLE",
        unit="ROTATION",
    )

    flip_x: BoolProperty(
        name="Flip X",
        description=(
            "Flip the silhouette horizontally "
            "before projection"
        ),
        default=False,
    )

    weight: FloatProperty(
        name="Weight",
        description=(
            "Relative contribution of this "
            "projection"
        ),
        default=1.0,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )


# ---------------------------------------------------------
# Generic pipeline stage settings
# ---------------------------------------------------------

class BPT_PG_PipelineStageSettings(
    PropertyGroup
):
    """
    Persistent Blender-side configuration for one pipeline
    stage.

    This class is intentionally generic.

    The UI must not need dedicated properties such as:

        sdf_enabled
        uv_bake_enabled
        autorig_enabled

    Instead each pipeline stage owns:

        enabled
        implementation_id
        expanded

    and the selected implementation owns its own detailed
    parameters.
    """

    enabled: BoolProperty(
        name="Enabled",
        description=(
            "Enable this pipeline stage"
        ),
        default=True,
    )

    implementation_id: StringProperty(
        name="Implementation",
        description=(
            "Stable identifier of the implementation "
            "selected for this pipeline stage"
        ),
        default="",
    )

    expanded: BoolProperty(
        name="Expanded",
        description=(
            "Show this pipeline stage configuration"
        ),
        default=True,
    )


# ---------------------------------------------------------
# Pipeline UI / selection settings
# ---------------------------------------------------------

class BPT_PG_PipelineSettings(
    PropertyGroup
):
    """
    Persistent configuration for the complete Meshvenn
    product pipeline.

    INPUT
        ↓
    GEOMETRY
        ↓
    MATERIAL
        ↓
    RIG
        ↓
    EXPORT
    """

    initialized: BoolProperty(
        name="Pipeline Initialized",
        default=False,
        options={
            "HIDDEN",
        },
    )

    input_stage: PointerProperty(
        name="Input",
        type=(
            BPT_PG_PipelineStageSettings
        ),
    )

    geometry_stage: PointerProperty(
        name="Geometry",
        type=(
            BPT_PG_PipelineStageSettings
        ),
    )

    material_stage: PointerProperty(
        name="Material",
        type=(
            BPT_PG_PipelineStageSettings
        ),
    )

    rig_stage: PointerProperty(
        name="Rig",
        type=(
            BPT_PG_PipelineStageSettings
        ),
    )

    export_stage: PointerProperty(
        name="Export",
        type=(
            BPT_PG_PipelineStageSettings
        ),
    )

    advanced_expanded: BoolProperty(
        name="Advanced",
        description=(
            "Show advanced pipeline configuration"
        ),
        default=False,
    )

    diagnostics_expanded: BoolProperty(
        name="Diagnostics",
        description=(
            "Show pipeline diagnostics"
        ),
        default=False,
    )


# ---------------------------------------------------------
# Main add-on settings
# ---------------------------------------------------------

class BPT_PG_Settings(
    PropertyGroup
):
    # -----------------------------------------------------
    # General pipeline
    # -----------------------------------------------------

    pipeline: PointerProperty(
        name="Pipeline",
        type=(
            BPT_PG_PipelineSettings
        ),
    )

    # -----------------------------------------------------
    # Input / projection configuration
    #
    # Existing properties are intentionally retained during
    # the pipeline migration.
    # -----------------------------------------------------

    projections: CollectionProperty(
        name="Projections",
        description=(
            "Projection views used for reconstruction"
        ),
        type=BPT_PG_ProjectionView,
    )

    active_projection_index: IntProperty(
        name="Active Projection Index",
        default=0,
        min=0,
    )

    alpha_threshold: FloatProperty(
        name="Threshold",
        description=(
            "Alpha threshold used to determine "
            "silhouette occupancy"
        ),
        default=0.1,
        min=0.0,
        max=1.0,
        subtype="FACTOR",
    )

    # -----------------------------------------------------
    # Geometry configuration
    #
    # These fields remain directly on BPT_PG_Settings for
    # compatibility with the current Native C++ operator.
    #
    # Concrete implementation-specific settings can later
    # move behind dedicated implementation PropertyGroups
    # without changing the general pipeline UI contract.
    # -----------------------------------------------------

    resolution: IntProperty(
        name="Resolution",
        description=(
            "Native voxel resolution of the "
            "generated volume"
        ),
        default=96,
        min=16,
        max=256,
    )

    symmetry_x: BoolProperty(
        name="Symmetry X",
        description=(
            "Force symmetry along the X axis "
            "after reconstruction"
        ),
        default=False,
    )

    thread_count: IntProperty(
        name="Threads",
        description=(
            "Native worker threads. "
            "0 uses automatic CPU detection"
        ),
        default=0,
        min=0,
        max=256,
    )

    # -----------------------------------------------------
    # Output normalization
    # -----------------------------------------------------

    normalize_height: BoolProperty(
        name="Normalize Height",
        description=(
            "Normalize the generated character "
            "to a predictable height"
        ),
        default=True,
    )

    target_height: FloatProperty(
        name="Target Height",
        description=(
            "Target generated character height "
            "in Blender units"
        ),
        default=2.0,
        min=0.1,
        max=100.0,
    )

    # -----------------------------------------------------
    # Legacy engine selector
    #
    # Keep this until BPT_OT_GenerateCharacter has been
    # migrated to PipelineRunner.
    #
    # Removing it now would break the existing UI/operator.
    # -----------------------------------------------------

    generation_mode: EnumProperty(
        name="Engine",
        description=(
            "Legacy reconstruction engine selector"
        ),
        items=(
            (
                "NATIVE_CPP",
                "Native C++",
                (
                    "Multithreaded native C++ "
                    "silhouette reconstruction"
                ),
            ),
        ),
        default="NATIVE_CPP",
    )


# ---------------------------------------------------------
# Pipeline stage mapping
# ---------------------------------------------------------

PIPELINE_STAGE_PROPERTY_NAMES: dict[
    PipelineStage,
    str,
] = {
    PipelineStage.INPUT:
        "input_stage",

    PipelineStage.GEOMETRY:
        "geometry_stage",

    PipelineStage.MATERIAL:
        "material_stage",

    PipelineStage.RIG:
        "rig_stage",

    PipelineStage.EXPORT:
        "export_stage",
}


PIPELINE_STAGE_DEFAULTS: dict[
    PipelineStage,
    tuple[
        str,
        bool,
        bool,
    ],
] = {
    # implementation id
    # enabled
    # expanded

    PipelineStage.INPUT: (
        DEFAULT_INPUT_IMPLEMENTATION_ID,
        True,
        True,
    ),

    PipelineStage.GEOMETRY: (
        DEFAULT_GEOMETRY_IMPLEMENTATION_ID,
        True,
        True,
    ),

    PipelineStage.MATERIAL: (
        DEFAULT_MATERIAL_IMPLEMENTATION_ID,
        True,
        True,
    ),

    PipelineStage.RIG: (
        DEFAULT_RIG_IMPLEMENTATION_ID,
        False,
        False,
    ),

    PipelineStage.EXPORT: (
        DEFAULT_EXPORT_IMPLEMENTATION_ID,
        False,
        False,
    ),
}


# ---------------------------------------------------------
# Pipeline settings helpers
# ---------------------------------------------------------

def pipeline_stage_settings(
    settings: BPT_PG_Settings,
    stage: PipelineStage,
) -> BPT_PG_PipelineStageSettings:
    """
    Return the persistent settings corresponding to a
    PipelineStage.

    UI and operators should use this helper rather than
    hardcoding `settings.pipeline.geometry_stage`, etc.
    """

    normalized_stage = (
        PipelineStage(
            stage
        )
    )

    property_name = (
        PIPELINE_STAGE_PROPERTY_NAMES[
            normalized_stage
        ]
    )

    return getattr(
        settings.pipeline,
        property_name,
    )


def ensure_pipeline_defaults(
    settings: BPT_PG_Settings,
) -> None:
    """
    Initialize the general pipeline only once.

    `initialized` prevents Blender load/update timers from
    overwriting user selections later.

    This is also the migration path for .blend files created
    before the generic pipeline existed.
    """

    pipeline = (
        settings.pipeline
    )

    if pipeline.initialized:
        return

    for (
        stage,
        (
            implementation_id,
            enabled,
            expanded,
        ),
    ) in (
        PIPELINE_STAGE_DEFAULTS
        .items()
    ):
        stage_settings = (
            pipeline_stage_settings(
                settings,
                stage,
            )
        )

        stage_settings.implementation_id = (
            implementation_id
        )

        stage_settings.enabled = (
            enabled
        )

        stage_settings.expanded = (
            expanded
        )

    pipeline.advanced_expanded = False

    pipeline.diagnostics_expanded = False

    pipeline.initialized = True


def reset_pipeline_defaults(
    settings: BPT_PG_Settings,
) -> None:
    """
    Reset only the general pipeline selection state.

    Projection images and implementation-specific generation
    parameters are intentionally left untouched.
    """

    pipeline = (
        settings.pipeline
    )

    pipeline.initialized = False

    ensure_pipeline_defaults(
        settings
    )


def set_pipeline_implementation(
    settings: BPT_PG_Settings,
    stage: PipelineStage,
    implementation_id: str,
) -> None:
    """
    Persist a user implementation selection.

    Empty strings are allowed here because optional stages
    such as RIG and EXPORT may not yet have an implementation
    selected.

    PipelinePlan construction will reject an enabled stage
    whose implementation is empty.
    """

    stage_settings = (
        pipeline_stage_settings(
            settings,
            stage,
        )
    )

    stage_settings.implementation_id = (
        str(
            implementation_id
        ).strip()
    )


def get_pipeline_implementation(
    settings: BPT_PG_Settings,
    stage: PipelineStage,
) -> str:
    return (
        pipeline_stage_settings(
            settings,
            stage,
        )
        .implementation_id
        .strip()
    )


# ---------------------------------------------------------
# PipelinePlan bridge
# ---------------------------------------------------------

def build_pipeline_plan(
    settings: BPT_PG_Settings,
) -> PipelinePlan:
    """
    Convert persistent Blender settings into the pure-Python
    PipelinePlan consumed by PipelineRunner.

    This is the boundary between Blender UI state and the
    generic pipeline core.
    """

    ensure_pipeline_defaults(
        settings
    )

    selections: list[
        PipelineStageSelection
    ] = []

    for stage in (
        PipelineStage
    ):
        stage_settings = (
            pipeline_stage_settings(
                settings,
                stage,
            )
        )

        implementation_id = (
            stage_settings
            .implementation_id
            .strip()
        )

        # -------------------------------------------------
        # An optional disabled stage without any selected
        # implementation simply does not participate in the
        # execution plan.
        # -------------------------------------------------

        if (
            not implementation_id
            and not stage_settings.enabled
        ):
            continue

        # -------------------------------------------------
        # Enabled stage with no implementation is a genuine
        # configuration error.
        #
        # Failing here gives the Blender operator a clear
        # user-facing message instead of manufacturing an
        # invalid PipelineStageSelection.
        # -------------------------------------------------

        if (
            stage_settings.enabled
            and not implementation_id
        ):
            raise ValueError(
                (
                    f'Pipeline stage "{stage.value}" '
                    "is enabled but has no "
                    "implementation selected."
                )
            )

        # -------------------------------------------------
        # Disabled stage with a remembered implementation
        # remains in the plan as disabled.
        #
        # This preserves the user's selection when they
        # temporarily toggle the stage off.
        # -------------------------------------------------

        if implementation_id:
            selections.append(
                PipelineStageSelection(
                    stage=stage,
                    implementation_id=(
                        implementation_id
                    ),
                    enabled=(
                        stage_settings
                        .enabled
                    ),
                )
            )

    return PipelinePlan(
        selections=tuple(
            selections
        )
    )


# ---------------------------------------------------------
# Projection defaults
# ---------------------------------------------------------

def ensure_default_projections(
    settings: BPT_PG_Settings,
) -> None:
    if len(
        settings.projections
    ) > 0:
        return

    defaults = (
        (
            "Front",
            0.0,
            0.0,
            False,
        ),
        (
            "Right",
            90.0,
            0.0,
            False,
        ),
        (
            "Back",
            180.0,
            0.0,
            False,
        ),
        (
            "Top",
            0.0,
            90.0,
            False,
        ),
    )

    for (
        name,
        azimuth_deg,
        elevation_deg,
        flip_x,
    ) in defaults:
        item = (
            settings
            .projections
            .add()
        )

        item.name = (
            name
        )

        item.azimuth = (
            math.radians(
                azimuth_deg
            )
        )

        item.elevation = (
            math.radians(
                elevation_deg
            )
        )

        item.flip_x = (
            flip_x
        )

        item.enabled = (
            name
            in {
                "Front",
                "Right",
            }
        )


# ---------------------------------------------------------
# Scene initialization
# ---------------------------------------------------------

def ensure_scene_defaults(
    scene: bpy.types.Scene,
) -> None:
    settings = getattr(
        scene,
        "bpt_settings",
        None,
    )

    if settings is None:
        return

    ensure_default_projections(
        settings
    )

    ensure_pipeline_defaults(
        settings
    )


def _ensure_scene_defaults() -> None:
    """
    Timer callback used after add-on registration.

    Initialize every loaded scene, not only the active one,
    so switching scenes later cannot expose an uninitialized
    pipeline.
    """

    for scene in tuple(
        bpy.data.scenes
    ):
        ensure_scene_defaults(
            scene
        )


# ---------------------------------------------------------
# Classes
# ---------------------------------------------------------

CLASSES = (
    BPT_PG_ProjectionView,

    BPT_PG_PipelineStageSettings,

    BPT_PG_PipelineSettings,

    BPT_PG_Settings,
)


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------

def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(
            cls
        )

    bpy.types.Scene.bpt_settings = (
        PointerProperty(
            type=BPT_PG_Settings,
        )
    )

    if not bpy.app.timers.is_registered(
        _ensure_scene_defaults
    ):
        bpy.app.timers.register(
            _ensure_scene_defaults,
            first_interval=0.1,
        )


def unregister() -> None:
    if bpy.app.timers.is_registered(
        _ensure_scene_defaults
    ):
        bpy.app.timers.unregister(
            _ensure_scene_defaults
        )

    if hasattr(
        bpy.types.Scene,
        "bpt_settings",
    ):
        del bpy.types.Scene.bpt_settings

    for cls in reversed(
        CLASSES
    ):
        bpy.utils.unregister_class(
            cls
        )