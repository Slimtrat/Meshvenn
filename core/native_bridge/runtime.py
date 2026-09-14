from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Iterable

from ..native_loader import load_native_library
from .abi import (
    BptMeshOptions,
    BptMeshResult,
    BptProjectionInput,
    BptScanOptions,
    BptVisualHullSessionPtr,
    BptVolumeResult,
)
from .conversion import (
    _build_projection_array,
    _build_projection_input,
    _copy_mesh_result,
    _copy_volume_result,
    _native_volume_from_python,
)
from .errors import MESH_MODE_BLOCKS, NativeCoreError, normalize_mesh_mode
from .models import NativeMesh, NativeProjection, NativeVolume


class NativeCore:

    def __init__(self, library_path: Path | None = None) -> None:
        self.lib = load_native_library(library_path)
        self._has_extended_mesh_api = False
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        lib = self.lib
        lib.bpt_visual_hull_create.argtypes = [
            ctypes.POINTER(BptScanOptions),
            ctypes.POINTER(BptVisualHullSessionPtr),
        ]
        lib.bpt_visual_hull_create.restype = ctypes.c_int32
        lib.bpt_visual_hull_apply_projection.argtypes = [
            BptVisualHullSessionPtr,
            ctypes.POINTER(BptProjectionInput),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lib.bpt_visual_hull_apply_projection.restype = ctypes.c_int32
        lib.bpt_visual_hull_snapshot.argtypes = [
            BptVisualHullSessionPtr,
            ctypes.POINTER(BptVolumeResult),
        ]
        lib.bpt_visual_hull_snapshot.restype = ctypes.c_int32
        lib.bpt_visual_hull_destroy.argtypes = [BptVisualHullSessionPtr]
        lib.bpt_visual_hull_destroy.restype = None
        lib.bpt_build_visual_hull.argtypes = [
            ctypes.POINTER(BptProjectionInput),
            ctypes.c_size_t,
            ctypes.POINTER(BptScanOptions),
            ctypes.POINTER(BptVolumeResult),
        ]
        lib.bpt_build_visual_hull.restype = ctypes.c_int32
        lib.bpt_build_surface_mesh.argtypes = [
            ctypes.POINTER(BptVolumeResult),
            ctypes.c_float,
            ctypes.c_uint8,
            ctypes.POINTER(BptMeshResult),
        ]
        lib.bpt_build_surface_mesh.restype = ctypes.c_int32
        extended_mesh_api = getattr(lib, "bpt_build_surface_mesh_ex", None)
        if extended_mesh_api is not None:
            extended_mesh_api.argtypes = [
                ctypes.POINTER(BptVolumeResult),
                ctypes.POINTER(BptMeshOptions),
                ctypes.POINTER(BptMeshResult),
            ]
            extended_mesh_api.restype = ctypes.c_int32
            self._has_extended_mesh_api = True
        lib.bpt_free_volume.argtypes = [ctypes.POINTER(BptVolumeResult)]
        lib.bpt_free_volume.restype = None
        lib.bpt_free_mesh.argtypes = [ctypes.POINTER(BptMeshResult)]
        lib.bpt_free_mesh.restype = None
        lib.bpt_result_message.argtypes = [ctypes.c_int32]
        lib.bpt_result_message.restype = ctypes.c_char_p

    def _check(self, code: int) -> None:
        if code == 0:
            return
        raw_message = self.lib.bpt_result_message(code)
        message = raw_message.decode("utf-8") if raw_message else "Unknown native error"
        raise NativeCoreError(code, message)

    def create_session(
        self, *, resolution: int, symmetry_x: bool = False, thread_count: int = 0
    ) -> "NativeVisualHullSession":
        return NativeVisualHullSession(
            core=self,
            resolution=resolution,
            symmetry_x=symmetry_x,
            thread_count=thread_count,
        )

    def build_visual_hull(
        self,
        projections: Iterable[NativeProjection],
        *,
        resolution: int,
        symmetry_x: bool = False,
        thread_count: int = 0,
    ) -> NativeVolume:
        projection_list = list(projections)
        if len(projection_list) < 2:
            raise ValueError("At least two projections are required.")
        native_array, keepalive = _build_projection_array(projection_list)
        options = BptScanOptions(
            resolution=resolution,
            symmetry_x=1 if symmetry_x else 0,
            reserved_0=0,
            reserved_1=0,
            reserved_2=0,
            thread_count=thread_count,
        )
        result = BptVolumeResult()
        code = self.lib.bpt_build_visual_hull(
            native_array,
            len(projection_list),
            ctypes.byref(options),
            ctypes.byref(result),
        )
        _ = keepalive
        self._check(code)
        try:
            return _copy_volume_result(result)
        finally:
            self.lib.bpt_free_volume(ctypes.byref(result))

    def build_surface_mesh(
        self,
        volume: NativeVolume,
        *,
        voxel_size: float = 1.0,
        center_xy: bool = True,
        mesh_mode: str = "blocks",
    ) -> NativeMesh:
        normalized_mode, native_mode = normalize_mesh_mode(mesh_mode)
        if voxel_size <= 0.0:
            raise ValueError("voxel_size must be greater than zero.")
        native_volume, keepalive = _native_volume_from_python(volume)
        result = BptMeshResult()
        if native_mode == MESH_MODE_BLOCKS:
            code = self.lib.bpt_build_surface_mesh(
                ctypes.byref(native_volume),
                float(voxel_size),
                1 if center_xy else 0,
                ctypes.byref(result),
            )
        else:
            if not self._has_extended_mesh_api:
                raise NativeCoreError(
                    1,
                    f'The loaded native library does not expose bpt_build_surface_mesh_ex(). Mesh mode "{normalized_mode}" requires a newer native build.',
                )
            options = BptMeshOptions(
                voxel_size=float(voxel_size),
                mode=native_mode,
                center_xy=1 if center_xy else 0,
                reserved_0=0,
                reserved_1=0,
                reserved_2=0,
            )
            code = self.lib.bpt_build_surface_mesh_ex(
                ctypes.byref(native_volume), ctypes.byref(options), ctypes.byref(result)
            )
        _ = keepalive
        self._check(code)
        try:
            return _copy_mesh_result(result)
        finally:
            self.lib.bpt_free_mesh(ctypes.byref(result))


class NativeVisualHullSession:

    def __init__(
        self,
        *,
        core: NativeCore,
        resolution: int,
        symmetry_x: bool = False,
        thread_count: int = 0,
    ) -> None:
        self.core = core
        self._session = BptVisualHullSessionPtr()
        self._closed = False
        options = BptScanOptions(
            resolution=resolution,
            symmetry_x=1 if symmetry_x else 0,
            reserved_0=0,
            reserved_1=0,
            reserved_2=0,
            thread_count=thread_count,
        )
        code = self.core.lib.bpt_visual_hull_create(
            ctypes.byref(options), ctypes.byref(self._session)
        )
        self.core._check(code)

    def apply_projection(self, projection: NativeProjection) -> int:
        self._ensure_open()
        native_projection, keepalive = _build_projection_input(projection)
        surviving = ctypes.c_size_t()
        code = self.core.lib.bpt_visual_hull_apply_projection(
            self._session, ctypes.byref(native_projection), ctypes.byref(surviving)
        )
        _ = keepalive
        self.core._check(code)
        return int(surviving.value)

    def snapshot(self) -> NativeVolume:
        self._ensure_open()
        result = BptVolumeResult()
        code = self.core.lib.bpt_visual_hull_snapshot(
            self._session, ctypes.byref(result)
        )
        self.core._check(code)
        try:
            return _copy_volume_result(result)
        finally:
            self.core.lib.bpt_free_volume(ctypes.byref(result))

    def close(self) -> None:
        if self._closed:
            return
        if self._session:
            self.core.lib.bpt_visual_hull_destroy(self._session)
        self._session = BptVisualHullSessionPtr()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Native visual hull session is already closed.")

    def __enter__(self) -> "NativeVisualHullSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
