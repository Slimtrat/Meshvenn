from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .masks import BinaryMask
from .native_loader import load_native_library


# ---------------------------------------------------------
# ctypes aliases
# ---------------------------------------------------------

_c_uint8_p = ctypes.POINTER(ctypes.c_uint8)
_c_uint32_p = ctypes.POINTER(ctypes.c_uint32)
_c_float_p = ctypes.POINTER(ctypes.c_float)


# ---------------------------------------------------------
# Native structs
# ---------------------------------------------------------

class BptProjectionInput(ctypes.Structure):
    _fields_ = [
        ("mask", _c_uint8_p),
        ("width", ctypes.c_int32),
        ("height", ctypes.c_int32),
        ("azimuth_degrees", ctypes.c_float),
        ("elevation_degrees", ctypes.c_float),
        ("flip_x", ctypes.c_uint8),
        ("reserved_0", ctypes.c_uint8),
        ("reserved_1", ctypes.c_uint8),
        ("reserved_2", ctypes.c_uint8),
    ]


class BptScanOptions(ctypes.Structure):
    _fields_ = [
        ("resolution", ctypes.c_int32),
        ("symmetry_x", ctypes.c_uint8),
        ("reserved_0", ctypes.c_uint8),
        ("reserved_1", ctypes.c_uint8),
        ("reserved_2", ctypes.c_uint8),
        ("thread_count", ctypes.c_int32),
    ]


class BptVolumeResult(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_int32),
        ("depth", ctypes.c_int32),
        ("height", ctypes.c_int32),
        ("values", _c_uint8_p),
        ("value_count", ctypes.c_size_t),
        ("occupied_count", ctypes.c_size_t),
        ("has_bounds", ctypes.c_uint8),
        ("reserved_0", ctypes.c_uint8),
        ("reserved_1", ctypes.c_uint8),
        ("reserved_2", ctypes.c_uint8),
        ("min_x", ctypes.c_int32),
        ("max_x", ctypes.c_int32),
        ("min_y", ctypes.c_int32),
        ("max_y", ctypes.c_int32),
        ("min_z", ctypes.c_int32),
        ("max_z", ctypes.c_int32),
    ]


class BptMeshResult(ctypes.Structure):
    _fields_ = [
        ("vertices", _c_float_p),
        ("vertex_float_count", ctypes.c_size_t),
        ("indices", _c_uint32_p),
        ("index_count", ctypes.c_size_t),
        ("polygon_starts", _c_uint32_p),
        ("polygon_sizes", _c_uint8_p),
        ("polygon_count", ctypes.c_size_t),
    ]


class BptVisualHullSession(ctypes.Structure):
    pass


BptVisualHullSessionPtr = ctypes.POINTER(BptVisualHullSession)


# ---------------------------------------------------------
# Python-facing data
# ---------------------------------------------------------

@dataclass(frozen=True)
class NativeProjection:
    mask: BinaryMask
    azimuth_degrees: float
    elevation_degrees: float = 0.0
    flip_x: bool = False


@dataclass(frozen=True)
class NativeVolume:
    width: int
    depth: int
    height: int
    values: bytes
    occupied_count: int
    bounds: tuple[int, int, int, int, int, int] | None


@dataclass(frozen=True)
class NativeMesh:
    vertices: tuple[float, ...]
    indices: tuple[int, ...]
    polygon_starts: tuple[int, ...]
    polygon_sizes: tuple[int, ...]

    @property
    def vertex_count(self) -> int:
        return len(self.vertices) // 3

    @property
    def polygon_count(self) -> int:
        return len(self.polygon_sizes)


# ---------------------------------------------------------
# Errors
# ---------------------------------------------------------

class NativeCoreError(RuntimeError):
    def __init__(
        self,
        code: int,
        message: str,
    ) -> None:
        super().__init__(
            f"Native core error {code}: {message}"
        )
        self.code = code


# ---------------------------------------------------------
# Library wrapper
# ---------------------------------------------------------

class NativeCore:
    def __init__(
        self,
        library_path: Path | None = None,
    ) -> None:
        self.lib = load_native_library(
            library_path
        )

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

        lib.bpt_visual_hull_destroy.argtypes = [
            BptVisualHullSessionPtr,
        ]
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

        lib.bpt_free_volume.argtypes = [
            ctypes.POINTER(BptVolumeResult),
        ]
        lib.bpt_free_volume.restype = None

        lib.bpt_free_mesh.argtypes = [
            ctypes.POINTER(BptMeshResult),
        ]
        lib.bpt_free_mesh.restype = None

        lib.bpt_result_message.argtypes = [
            ctypes.c_int32,
        ]
        lib.bpt_result_message.restype = ctypes.c_char_p

    def _check(self, code: int) -> None:
        if code == 0:
            return

        raw_message = self.lib.bpt_result_message(
            code
        )

        message = (
            raw_message.decode("utf-8")
            if raw_message
            else "Unknown native error"
        )

        raise NativeCoreError(
            code,
            message,
        )

    def create_session(
        self,
        *,
        resolution: int,
        symmetry_x: bool = False,
        thread_count: int = 0,
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
        projection_list = list(
            projections
        )

        if len(projection_list) < 2:
            raise ValueError(
                "At least two projections are required."
            )

        native_array, keepalive = _build_projection_array(
            projection_list
        )

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
            return _copy_volume_result(
                result
            )
        finally:
            self.lib.bpt_free_volume(
                ctypes.byref(result)
            )

    def build_surface_mesh(
        self,
        volume: NativeVolume,
        *,
        voxel_size: float = 1.0,
        center_xy: bool = True,
    ) -> NativeMesh:
        native_volume, keepalive = _native_volume_from_python(
            volume
        )

        result = BptMeshResult()

        code = self.lib.bpt_build_surface_mesh(
            ctypes.byref(native_volume),
            float(voxel_size),
            1 if center_xy else 0,
            ctypes.byref(result),
        )

        _ = keepalive
        self._check(code)

        try:
            return _copy_mesh_result(
                result
            )
        finally:
            self.lib.bpt_free_mesh(
                ctypes.byref(result)
            )


# ---------------------------------------------------------
# Incremental session
# ---------------------------------------------------------

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
            ctypes.byref(options),
            ctypes.byref(self._session),
        )

        self.core._check(code)

    def apply_projection(
        self,
        projection: NativeProjection,
    ) -> int:
        self._ensure_open()

        native_projection, keepalive = _build_projection_input(
            projection
        )

        surviving = ctypes.c_size_t()

        code = self.core.lib.bpt_visual_hull_apply_projection(
            self._session,
            ctypes.byref(native_projection),
            ctypes.byref(surviving),
        )

        _ = keepalive
        self.core._check(code)

        return int(
            surviving.value
        )

    def snapshot(self) -> NativeVolume:
        self._ensure_open()

        result = BptVolumeResult()

        code = self.core.lib.bpt_visual_hull_snapshot(
            self._session,
            ctypes.byref(result),
        )

        self.core._check(code)

        try:
            return _copy_volume_result(
                result
            )
        finally:
            self.core.lib.bpt_free_volume(
                ctypes.byref(result)
            )

    def close(self) -> None:
        if self._closed:
            return

        if self._session:
            self.core.lib.bpt_visual_hull_destroy(
                self._session
            )

        self._session = BptVisualHullSessionPtr()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError(
                "Native visual hull session is already closed."
            )

    def __enter__(
        self,
    ) -> "NativeVisualHullSession":
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# ---------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------

def _build_projection_input(
    projection: NativeProjection,
) -> tuple[
    BptProjectionInput,
    ctypes.Array,
]:
    raw = projection.mask.values

    buffer_type = ctypes.c_uint8 * len(raw)
    buffer = buffer_type.from_buffer_copy(
        raw
    )

    result = BptProjectionInput(
        mask=ctypes.cast(
            buffer,
            _c_uint8_p,
        ),
        width=projection.mask.width,
        height=projection.mask.height,
        azimuth_degrees=float(
            projection.azimuth_degrees
        ),
        elevation_degrees=float(
            projection.elevation_degrees
        ),
        flip_x=1 if projection.flip_x else 0,
        reserved_0=0,
        reserved_1=0,
        reserved_2=0,
    )

    return result, buffer


def _build_projection_array(
    projections: list[NativeProjection],
):
    native_inputs = []
    keepalive = []

    for projection in projections:
        native_input, buffer = _build_projection_input(
            projection
        )

        native_inputs.append(
            native_input
        )
        keepalive.append(
            buffer
        )

    array_type = (
        BptProjectionInput
        * len(native_inputs)
    )

    native_array = array_type(
        *native_inputs
    )

    keepalive.append(
        native_array
    )

    return native_array, keepalive


def _copy_volume_result(
    result: BptVolumeResult,
) -> NativeVolume:
    value_count = int(
        result.value_count
    )

    values = (
        ctypes.string_at(
            result.values,
            value_count,
        )
        if result.values
        else b""
    )

    bounds = None

    if result.has_bounds:
        bounds = (
            int(result.min_x),
            int(result.max_x),
            int(result.min_y),
            int(result.max_y),
            int(result.min_z),
            int(result.max_z),
        )

    return NativeVolume(
        width=int(result.width),
        depth=int(result.depth),
        height=int(result.height),
        values=values,
        occupied_count=int(
            result.occupied_count
        ),
        bounds=bounds,
    )


def _copy_mesh_result(
    result: BptMeshResult,
) -> NativeMesh:
    vertex_float_count = int(
        result.vertex_float_count
    )
    index_count = int(
        result.index_count
    )
    polygon_count = int(
        result.polygon_count
    )

    vertices = tuple(
        result.vertices[index]
        for index in range(
            vertex_float_count
        )
    ) if result.vertices else ()

    indices = tuple(
        int(
            result.indices[index]
        )
        for index in range(
            index_count
        )
    ) if result.indices else ()

    polygon_starts = tuple(
        int(
            result.polygon_starts[index]
        )
        for index in range(
            polygon_count
        )
    ) if result.polygon_starts else ()

    polygon_sizes = tuple(
        int(
            result.polygon_sizes[index]
        )
        for index in range(
            polygon_count
        )
    ) if result.polygon_sizes else ()

    return NativeMesh(
        vertices=vertices,
        indices=indices,
        polygon_starts=polygon_starts,
        polygon_sizes=polygon_sizes,
    )


def _native_volume_from_python(
    volume: NativeVolume,
) -> tuple[
    BptVolumeResult,
    ctypes.Array,
]:
    raw = volume.values

    buffer_type = ctypes.c_uint8 * len(raw)
    buffer = buffer_type.from_buffer_copy(
        raw
    )

    result = BptVolumeResult(
        width=volume.width,
        depth=volume.depth,
        height=volume.height,
        values=ctypes.cast(
            buffer,
            _c_uint8_p,
        ),
        value_count=len(raw),
        occupied_count=volume.occupied_count,
        has_bounds=1 if volume.bounds else 0,
        reserved_0=0,
        reserved_1=0,
        reserved_2=0,
    )

    if volume.bounds:
        (
            result.min_x,
            result.max_x,
            result.min_y,
            result.max_y,
            result.min_z,
            result.max_z,
        ) = volume.bounds

    return result, buffer