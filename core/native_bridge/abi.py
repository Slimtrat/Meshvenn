from __future__ import annotations

import ctypes

_c_uint8_p = ctypes.POINTER(ctypes.c_uint8)

_c_uint32_p = ctypes.POINTER(ctypes.c_uint32)

_c_float_p = ctypes.POINTER(ctypes.c_float)


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


class BptMeshOptions(ctypes.Structure):
    _fields_ = [
        ("voxel_size", ctypes.c_float),
        ("mode", ctypes.c_int32),
        ("center_xy", ctypes.c_uint8),
        ("reserved_0", ctypes.c_uint8),
        ("reserved_1", ctypes.c_uint8),
        ("reserved_2", ctypes.c_uint8),
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
