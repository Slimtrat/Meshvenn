from __future__ import annotations

import math
import os
import re

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

from ..core.pipeline_contracts import (
    PipelineContext,
    PipelinePlan,
    PipelineStage,
    PIPELINE_STAGE_ORDER,
)
from ..core.pipeline_registry import PIPELINE_REGISTRY
from ..core.pipeline_runner import (
    PipelineExecutionReport,
    PipelineRunOptions,
    PipelineRunner,
)
from ..properties import (
    build_pipeline_plan,
    pipeline_stage_settings,
    reset_pipeline_defaults,
    set_pipeline_implementation,
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

IMAGE_FILTER = (
    "*.png;"
    "*.jpg;"
    "*.jpeg;"
    "*.webp;"
    "*.bmp;"
    "*.tif;"
    "*.tiff"
)

ANGLE_PATTERN = re.compile(
    r"(?<!\d)(\d{1,3})(?:deg|°)?(?!\d)",
    re.IGNORECASE,
)


PIPELINE_STAGE_ENUM_ITEMS = (
    (
        PipelineStage.INPUT.value,
        "Input",
        "Input preparation stage",
    ),
    (
        PipelineStage.GEOMETRY.value,
        "Geometry",
        "3D geometry reconstruction stage",
    ),
    (
        PipelineStage.MATERIAL.value,
        "Material",
        "Material generation stage",
    ),
    (
        PipelineStage.RIG.value,
        "Rig",
        "Rig generation stage",
    ),
    (
        PipelineStage.EXPORT.value,
        "Export",
        "Asset export stage",
    ),
)


RUNNABLE_STAGE_ENUM_ITEMS = (
    (
        PipelineStage.GEOMETRY.value,
        "Geometry",
        (
            "Run the pipeline through "
            "the Geometry stage"
        ),
    ),
    (
        PipelineStage.MATERIAL.value,
        "Material",
        (
            "Run the pipeline through "
            "the Material stage"
        ),
    ),
    (
        PipelineStage.RIG.value,
        "Rig",
        (
            "Run the pipeline through "
            "the Rig stage"
        ),
    ),
    (
        PipelineStage.EXPORT.value,
        "Export",
        (
            "Run the pipeline through "
            "the Export stage"
        ),
    ),
)
