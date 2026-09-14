from __future__ import annotations

import ctypes
from array import array

from .abi import (
    BptMeshResult,
    BptProjectionInput,
    BptVolumeResult,
    _c_float_p,
    _c_uint32_p,
    _c_uint8_p,
)
from .models import NativeMesh, NativeProjection, NativeVolume


def _build_projection_input(
    projection: NativeProjection,
) -> tuple[BptProjectionInput, ctypes.Array]:
    raw = projection.mask.values
    buffer_type = ctypes.c_uint8 * len(raw)
    buffer = buffer_type.from_buffer_copy(raw)
    result = BptProjectionInput(
        mask=ctypes.cast(buffer, _c_uint8_p),
        width=projection.mask.width,
        height=projection.mask.height,
        azimuth_degrees=float(projection.azimuth_degrees),
        elevation_degrees=float(projection.elevation_degrees),
        flip_x=1 if projection.flip_x else 0,
        reserved_0=0,
        reserved_1=0,
        reserved_2=0,
    )
    return (result, buffer)


def _build_projection_array(projections: list[NativeProjection]):
    native_inputs = []
    keepalive = []
    for projection in projections:
        native_input, buffer = _build_projection_input(projection)
        native_inputs.append(native_input)
        keepalive.append(buffer)
    array_type = BptProjectionInput * len(native_inputs)
    native_array = array_type(*native_inputs)
    keepalive.append(native_array)
    return (native_array, keepalive)


def _copy_volume_result(result: BptVolumeResult) -> NativeVolume:
    value_count = int(result.value_count)
    values = (
        ctypes.string_at(result.values, value_count)
        if result.values and value_count
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
        occupied_count=int(result.occupied_count),
        bounds=bounds,
    )


def _native_volume_from_python(
    volume: NativeVolume,
) -> tuple[BptVolumeResult, ctypes.Array]:
    raw = volume.values
    buffer_type = ctypes.c_uint8 * len(raw)
    buffer = buffer_type.from_buffer_copy(raw)
    result = BptVolumeResult(
        width=volume.width,
        depth=volume.depth,
        height=volume.height,
        values=ctypes.cast(buffer, _c_uint8_p),
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
    return (result, buffer)


def _copy_mesh_result(result: BptMeshResult) -> NativeMesh:
    """
    Copy native mesh buffers into compact Python arrays.

    This intentionally avoids per-element ctypes -> Python
    conversions. Each native buffer is copied once as raw
    memory, then exposed as a contiguous typed array suitable
    for Blender foreach_set().
    """
    vertex_float_count = int(result.vertex_float_count)
    index_count = int(result.index_count)
    polygon_count = int(result.polygon_count)
    vertices = _copy_float32_array(result.vertices, vertex_float_count)
    indices = _copy_uint32_array(result.indices, index_count)
    polygon_starts = _copy_uint32_array(result.polygon_starts, polygon_count)
    polygon_sizes = _copy_uint8_array(result.polygon_sizes, polygon_count)
    return NativeMesh(
        vertices=vertices,
        indices=indices,
        polygon_starts=polygon_starts,
        polygon_sizes=polygon_sizes,
    )


def _copy_float32_array(pointer: _c_float_p, count: int) -> array:
    result = array("f")
    if not pointer or count <= 0:
        return result
    if result.itemsize != 4:
        raise RuntimeError(
            "Python array('f') does not use 32-bit floats on this platform."
        )
    raw = ctypes.string_at(pointer, count * 4)
    result.frombytes(raw)
    return result


def _copy_uint32_array(pointer: _c_uint32_p, count: int) -> array:
    result = array("I")
    if not pointer or count <= 0:
        return result
    if result.itemsize != 4:
        raise RuntimeError(
            "Python array('I') does not use 32-bit unsigned integers on this platform."
        )
    raw = ctypes.string_at(pointer, count * 4)
    result.frombytes(raw)
    return result


def _copy_uint8_array(pointer: _c_uint8_p, count: int) -> array:
    result = array("B")
    if not pointer or count <= 0:
        return result
    raw = ctypes.string_at(pointer, count)
    result.frombytes(raw)
    return result
