from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeAlias




# =========================================================
# Types
# =========================================================

Vector2: TypeAlias = tuple[
    float,
    float,
]

Vector3: TypeAlias = tuple[
    float,
    float,
    float,
]

RGBA: TypeAlias = tuple[
    float,
    float,
    float,
    float,
]


# =========================================================
# Constants
# =========================================================

# Selected from the UV Bake resolution benchmark:
#
# 256:
#     too many subpixel UV triangles on dense generated
#     meshes.
#
# 512:
#     reaches the current texture-density target while
#     remaining suitable for interactive generation.
#
# 1024+:
#     retained as higher-quality explicit configurations,
#     but no longer the generic default.
DEFAULT_TEXTURE_SIZE = 512

DEFAULT_PADDING_PIXELS = 8

DEFAULT_SAMPLES_PER_AXIS = 1

DEFAULT_BACKGROUND_COLOR: RGBA = (
    0.0,
    0.0,
    0.0,
    0.0,
)

DEFAULT_BARYCENTRIC_EPSILON = 1e-8

DEFAULT_DEGENERATE_UV_EPSILON = 1e-12

MAX_TEXTURE_DIMENSION = 4096

MAX_PADDING_PIXELS = 128

MAX_SAMPLES_PER_AXIS = 4

NORMAL_EPSILON = 1e-12

COLOR_CHANNEL_COUNT = 4

UNVISITED_DISTANCE = 65535


# =========================================================
# Small helpers
# =========================================================
