from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any

import bpy

from ..core.geometry_contracts import (
    GeometrySurfaceOutput,
    require_geometry_surface_output,
)
from ..core.material_blend import (
    MaterialBlendConfig,
)
from ..core.material_visibility import (
    MeshVisibilityTester,
)
from ..core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..core.projected_material import (
    DEFAULT_FALLBACK_COLOR,
    blend_projected_color,
)
from ..core.uv_bake import (
    SurfaceColorSample,
    UVBakeConfig,
    UVBakeResult,
    UVBakeTriangle,
    UVBakeVertex,
    bake_uv_texture,
)



# =========================================================
# Constants
# =========================================================

IMPLEMENTATION_ID = (
    "uv-bake-v2"
)

MATERIAL_MODE = (
    "uv-bake-v2"
)


# ---------------------------------------------------------
# Product texture default
# ---------------------------------------------------------

DEFAULT_TEXTURE_SIZE = 512

DEFAULT_PADDING_PIXELS = 8

DEFAULT_SAMPLES_PER_AXIS = 1

DEFAULT_UV_LAYER_NAME = (
    "MeshvennUV"
)


# ---------------------------------------------------------
# Smart Project margin
#
# Blender's FRACTION margin is expressed in UV-space.
#
# UV Bake performs its own post-bake color dilation, so
# Smart Project only needs enough spacing to keep islands
# distinct.
#
# Maximum spacing:
#
#     256  -> 0.001953125
#     512  -> 0.0009765625
#     1024 -> 0.00048828125
#     4096 -> 0.0001220703125
#
# i.e. 0.5 texture texel maximum.
# ---------------------------------------------------------

DEFAULT_ISLAND_MARGIN = 0.02

MAX_SMART_PROJECT_MARGIN_TEXELS = 0.5


DEFAULT_ANGLE_LIMIT_DEGREES = 66.0

DEFAULT_REUSE_EXISTING_UV = False


DEFAULT_ENABLE_VISIBILITY = True

DEFAULT_ALLOW_BACKFACE_FALLBACK = True

DEFAULT_MIN_FACING = 0.10

DEFAULT_FACING_POWER = 2.0

DEFAULT_RELATIVE_SCORE_CUTOFF = 0.20

DEFAULT_MAX_CONTRIBUTORS = 3

DEFAULT_WEIGHT_POWER = 1.5


DEFAULT_ROUGHNESS = 0.65


# =========================================================
# Configuration
# =========================================================
