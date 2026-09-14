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
