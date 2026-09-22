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

from ..core.pipeline_contracts import PipelineStage
from .constants import *

from .base_groups import (
    BPT_PG_PipelineSettings,
    BPT_PG_PipelineStageSettings,
    BPT_PG_ProjectionView,
)

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
    #
    # Keep these historical names stable because existing
    # .blend files and scripts already use them.
    #
    # SDF has its own independent settings below.
    # =====================================================

    resolution: IntProperty(
        name="Resolution",
        description=(
            "Native Visual Hull voxel resolution"
        ),
        default=96,
        min=16,
        max=256,
    )

    symmetry_x: BoolProperty(
        name="Symmetry X",
        description=(
            "Force conservative X symmetry during "
            "Native Visual Hull reconstruction"
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

    # =====================================================
    # GEOMETRY — SDF Reconstruction V1
    #
    # These properties are intentionally separate from the
    # Native Visual Hull configuration.
    #
    # Switching implementation therefore preserves the
    # configuration of both engines independently.
    # =====================================================

    sdf_resolution: IntProperty(
        name="Resolution",
        description=(
            "Resolution of the dense signed-distance "
            "field. The current Python reference backend "
            "is limited to 160³ samples"
        ),
        default=(
            DEFAULT_SDF_RESOLUTION
        ),
        min=(
            MINIMUM_SDF_RESOLUTION
        ),
        max=(
            MAXIMUM_SDF_REFERENCE_RESOLUTION
        ),
        soft_max=128,
    )

    sdf_symmetry_x: BoolProperty(
        name="Symmetry X",
        description=(
            "Apply conservative X symmetry to every SDF "
            "projection constraint"
        ),
        default=(
            DEFAULT_SDF_SYMMETRY_X
        ),
    )

    sdf_smoothness: FloatProperty(
        name="Constraint Smoothness",
        description=(
            "Smooth the maximum used to intersect SDF "
            "projection constraints. 0 keeps the exact "
            "hard silhouette intersection"
        ),
        default=(
            DEFAULT_SDF_SMOOTHNESS
        ),
        min=0.0,
        max=2.0,
        soft_max=0.25,
        precision=4,
    )

    sdf_surface_offset: FloatProperty(
        name="Surface Offset",
        description=(
            "Expand or contract the reconstructed signed "
            "distance field before surface extraction. "
            "Positive values expand the surface"
        ),
        default=(
            DEFAULT_SDF_SURFACE_OFFSET
        ),
        min=-2.0,
        max=2.0,
        soft_min=-0.25,
        soft_max=0.25,
        precision=4,
    )

    sdf_iso_level: FloatProperty(
        name="Iso Level",
        description=(
            "Signed-distance value extracted as the "
            "surface. 0 is the natural SDF boundary"
        ),
        default=(
            DEFAULT_SDF_ISO_LEVEL
        ),
        min=-2.0,
        max=2.0,
        soft_min=-0.25,
        soft_max=0.25,
        precision=4,
    )

    # -----------------------------------------------------
    # Surface normal estimation
    #
    # Not currently drawn by the normal SDF UI because this
    # is an implementation-detail tuning parameter.
    #
    # Keeping it persistent makes it available to advanced
    # tooling and future diagnostics without hardcoding it.
    # -----------------------------------------------------

    sdf_gradient_step_scale: FloatProperty(
        name="Gradient Step",
        description=(
            "Sampling distance used to estimate SDF "
            "surface normals, expressed as a fraction "
            "of one scalar-grid interval"
        ),
        default=(
            DEFAULT_SDF_GRADIENT_STEP_SCALE
        ),
        min=0.05,
        max=2.0,
        soft_min=0.25,
        soft_max=1.0,
        precision=3,
    )

    # =====================================================
    # GEOMETRY — shared output normalization
    #
    # Both Native Visual Hull and SDF Reconstruction keep
    # their local projection coordinates untouched.
    #
    # Height normalization is applied at object level so
    # projection-dependent MATERIAL stages still see the
    # original reconstruction coordinate space.
    # =====================================================

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
    #
    # Do not add SDF here: the general pipeline selector is
    # authoritative for new implementations.
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
