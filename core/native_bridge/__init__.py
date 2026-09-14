"""Stable façade for the native C ABI and Python bridge."""

from .abi import (
    BptMeshOptions,
    BptMeshResult,
    BptProjectionInput,
    BptScanOptions,
    BptVisualHullSession,
    BptVisualHullSessionPtr,
    BptVolumeResult,
)
from .errors import (
    MESH_MODE_BLOCKS,
    MESH_MODE_BY_NAME,
    MESH_MODE_SURFACE_NETS,
    NativeCoreError,
    normalize_mesh_mode,
)
from .models import NativeMesh, NativeProjection, NativeVolume
from .runtime import NativeCore, NativeVisualHullSession

__all__ = (
    "BptMeshOptions",
    "BptMeshResult",
    "BptProjectionInput",
    "BptScanOptions",
    "BptVisualHullSession",
    "BptVisualHullSessionPtr",
    "BptVolumeResult",
    "MESH_MODE_BLOCKS",
    "MESH_MODE_BY_NAME",
    "MESH_MODE_SURFACE_NETS",
    "NativeCore",
    "NativeCoreError",
    "NativeMesh",
    "NativeProjection",
    "NativeVisualHullSession",
    "NativeVolume",
    "normalize_mesh_mode",
)
