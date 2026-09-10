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


# =========================================================
# Stable implementation defaults
# =========================================================

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


# =========================================================
# UV Bake defaults
#
# These values deliberately mirror implementations/uv_bake.py.
#
# Keep the implementation as the authority for runtime
# validation. These Blender properties only expose a safe
# persistent UI surface.
# =========================================================

DEFAULT_UV_BAKE_TEXTURE_SIZE = "512"

DEFAULT_UV_BAKE_PADDING_PIXELS = 8

DEFAULT_UV_BAKE_SAMPLES_PER_AXIS = "1"

DEFAULT_UV_BAKE_UV_LAYER_NAME = (
    "MeshvennUV"
)

DEFAULT_UV_BAKE_ISLAND_MARGIN = 0.02

DEFAULT_UV_BAKE_ANGLE_LIMIT_DEGREES = 66.0

DEFAULT_UV_BAKE_REUSE_EXISTING_UV = False


UV_BAKE_TEXTURE_SIZE_ITEMS = (
    (
        "512",
        "512 px",
        (
            "Recommended default for interactive "
            "Meshvenn generation. Balanced UV density, "
            "bake time and exported asset size."
        ),
    ),
    (
        "1024",
        "1024 px",
        (
            "High-quality texture for final export or "
            "meshes requiring additional texture density. "
            "Significantly higher bake cost."
        ),
    ),
    (
        "2048",
        "2048 px",
        (
            "Higher-detail texture with significantly "
            "more bake samples."
        ),
    ),
    (
        "4096",
        "4096 px",
        (
            "Maximum V2 texture resolution. "
            "High memory and bake cost."
        ),
    ),
)


UV_BAKE_SAMPLE_ITEMS = (
    (
        "1",
        "1×1",
        (
            "One projected-color evaluation per "
            "covered texel."
        ),
    ),
    (
        "2",
        "2×2",
        (
            "Four projected-color evaluations per "
            "covered texel."
        ),
    ),
    (
        "3",
        "3×3",
        (
            "Nine projected-color evaluations per "
            "covered texel."
        ),
    ),
    (
        "4",
        "4×4",
        (
            "Sixteen projected-color evaluations per "
            "covered texel. Expensive."
        ),
    ),
)


# =========================================================
# Projection view
# =========================================================

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


# =========================================================
# Generic pipeline stage settings
# =========================================================

class BPT_PG_PipelineStageSettings(
    PropertyGroup
):
    """
    Persistent Blender-side configuration for one pipeline
    stage.

    This class stays implementation-agnostic.

    Each stage owns:

        enabled
        implementation_id
        expanded

    while detailed implementation parameters live outside
    this generic contract.
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


# =========================================================
# Pipeline UI / selection settings
# =========================================================

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


# =========================================================
# Main add-on settings
# =========================================================

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

    # =====================================================
    # INPUT
    # =====================================================

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

    # =====================================================
    # GEOMETRY — Native Visual Hull
    # =====================================================

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

    # =====================================================
    # MATERIAL — UV Bake V2
    #
    # Flat properties are intentional for the current
    # migration.
    #
    # implementations/uv_bake.py reads these names
    # defensively and falls back to the same defaults when
    # loading an older .blend file.
    # =====================================================

    uv_bake_texture_size: EnumProperty(
        name="Texture Size",
        description=(
            "Resolution of the square UV texture "
            "generated by UV Bake V2"
        ),
        items=(
            UV_BAKE_TEXTURE_SIZE_ITEMS
        ),
        default=(
            DEFAULT_UV_BAKE_TEXTURE_SIZE
        ),
    )

    uv_bake_padding_pixels: IntProperty(
        name="Padding",
        description=(
            "Expand baked colors outside UV islands "
            "to protect seams during bilinear filtering "
            "and mipmapping"
        ),
        default=(
            DEFAULT_UV_BAKE_PADDING_PIXELS
        ),
        min=0,
        max=128,
        soft_max=32,
        subtype="PIXEL",
    )

    uv_bake_samples_per_axis: EnumProperty(
        name="Samples",
        description=(
            "Supersampling performed inside each "
            "covered texture pixel"
        ),
        items=(
            UV_BAKE_SAMPLE_ITEMS
        ),
        default=(
            DEFAULT_UV_BAKE_SAMPLES_PER_AXIS
        ),
    )

    uv_bake_reuse_existing_uv: BoolProperty(
        name="Reuse Existing UV",
        description=(
            "Use the mesh's active UV map instead of "
            "generating a new Smart UV Project layout"
        ),
        default=(
            DEFAULT_UV_BAKE_REUSE_EXISTING_UV
        ),
    )

    uv_bake_uv_layer_name: StringProperty(
        name="UV Layer",
        description=(
            "Name of the UV map created by "
            "UV Bake V2 when Smart UV Project is used"
        ),
        default=(
            DEFAULT_UV_BAKE_UV_LAYER_NAME
        ),
    )

    uv_bake_island_margin: FloatProperty(
        name="Island Margin",
        description=(
            "Fractional spacing between islands "
            "during Blender Smart UV Project"
        ),
        default=(
            DEFAULT_UV_BAKE_ISLAND_MARGIN
        ),
        min=0.0,
        max=1.0,
        soft_max=0.1,
        precision=3,
    )

    uv_bake_angle_limit_degrees: FloatProperty(
        name="Angle Limit",
        description=(
            "Angle threshold in degrees used by "
            "Blender Smart UV Project"
        ),
        default=(
            DEFAULT_UV_BAKE_ANGLE_LIMIT_DEGREES
        ),
        min=1.0,
        max=90.0,
        soft_min=30.0,
        soft_max=89.0,
        precision=1,
    )

    # =====================================================
    # Legacy selector
    #
    # Retained for compatibility with older .blend files and
    # callers. PipelineRunner is now the production path.
    # =====================================================

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


# =========================================================
# Pipeline stage mapping
# =========================================================

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


# =========================================================
# Pipeline settings helpers
# =========================================================

def pipeline_stage_settings(
    settings: BPT_PG_Settings,
    stage: PipelineStage,
) -> BPT_PG_PipelineStageSettings:
    """
    Return the persistent Blender settings corresponding to
    one PipelineStage.

    UI and operators use this instead of hardcoding:

        settings.pipeline.geometry_stage

    etc.
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
    Initialize generic pipeline selections exactly once.

    This is also the migration path for .blend files created
    before the generic pipeline existed.

    Implementation-specific settings such as UV Bake V2 are
    Blender properties with their own defaults and therefore
    do not need explicit migration here.
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
    Reset only the generic pipeline selection state.

    Projection images and implementation-specific settings
    are deliberately preserved.
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
    Persist one user-selected pipeline implementation.

    Empty identifiers remain valid here because optional
    stages such as RIG and EXPORT may have no implementation
    selected.
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


# =========================================================
# PipelinePlan bridge
# =========================================================

def build_pipeline_plan(
    settings: BPT_PG_Settings,
) -> PipelinePlan:
    """
    Convert persistent Blender state into the pure Python
    PipelinePlan consumed by PipelineRunner.
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
        # Disabled optional stage with no remembered
        # implementation does not participate.
        # -------------------------------------------------

        if (
            not implementation_id
            and not stage_settings.enabled
        ):
            continue

        # -------------------------------------------------
        # Enabled stage without implementation is a genuine
        # configuration error.
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
        # Disabled stage with a remembered implementation is
        # retained as disabled so toggling it does not erase
        # the user's selection.
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


# =========================================================
# Projection defaults
# =========================================================

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


# =========================================================
# Scene initialization
# =========================================================

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

    Initialize every loaded scene rather than only the active
    scene so switching scenes cannot expose an uninitialized
    pipeline.
    """

    for scene in tuple(
        bpy.data.scenes
    ):
        ensure_scene_defaults(
            scene
        )


# =========================================================
# Classes
# =========================================================

CLASSES = (
    BPT_PG_ProjectionView,

    BPT_PG_PipelineStageSettings,

    BPT_PG_PipelineSettings,

    BPT_PG_Settings,
)


# =========================================================
# Registration
# =========================================================

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