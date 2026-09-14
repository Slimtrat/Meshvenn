"""Native Visual Hull geometry implementation façade."""

from .config import NativeVisualHullConfig
from .constants import (
    DEFAULT_CENTER_XY,
    DEFAULT_MESH_MODE,
    DEFAULT_MESH_NAME,
    DEFAULT_OBJECT_NAME,
    DEFAULT_VOXEL_SIZE,
    IMPLEMENTATION_ID,
)
from .implementation import NativeVisualHullImplementation
from .output import NativeVisualHullOutput, require_native_visual_hull_output

__all__ = (
    "DEFAULT_CENTER_XY",
    "DEFAULT_MESH_MODE",
    "DEFAULT_MESH_NAME",
    "DEFAULT_OBJECT_NAME",
    "DEFAULT_VOXEL_SIZE",
    "IMPLEMENTATION_ID",
    "NativeVisualHullConfig",
    "NativeVisualHullImplementation",
    "NativeVisualHullOutput",
    "require_native_visual_hull_output",
)
