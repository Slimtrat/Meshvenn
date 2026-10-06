"""Small strict GLB/BIN reader for independent modular export validation."""

from __future__ import annotations

import json
import math
from pathlib import Path
import struct


_COMPONENTS = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
               5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
_SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
MAX_GLB_BYTES = 256 * 1024 * 1024


def _integer(value, label, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"GLB {label} must be an integer >= {minimum}.")
    return value


def read_glb(path):
    """Return validated glTF JSON and the single embedded binary buffer."""
    source = Path(path)
    size = source.stat().st_size
    if not 20 <= size <= MAX_GLB_BYTES:
        raise ValueError("Modular GLB size is outside the supported validation budget.")
    with source.open("rb") as stream:
        payload = stream.read(MAX_GLB_BYTES + 1)
    if len(payload) > MAX_GLB_BYTES:
        raise ValueError("Modular GLB grew beyond the supported validation budget.")
    magic, version, length = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2 or length != len(payload):
        raise ValueError("Invalid modular GLB header.")
    chunks = []
    offset = 12
    while offset < length:
        if offset + 8 > length:
            raise ValueError("Truncated modular GLB chunk header.")
        count, kind = struct.unpack_from("<II", payload, offset)
        offset += 8
        if count % 4 or offset + count > length:
            raise ValueError("Invalid modular GLB chunk bounds or alignment.")
        chunks.append((kind, payload[offset:offset + count]))
        offset += count
    if not chunks or chunks[0][0] != 0x4E4F534A:
        raise ValueError("Modular GLB must start with JSON.")
    if len(chunks) != 2 or chunks[1][0] != 0x004E4942:
        raise ValueError("Modular GLB requires exactly one JSON and one BIN chunk.")
    document = json.loads(chunks[0][1].rstrip(b" \t\r\n\0").decode("utf-8"))
    if not isinstance(document, dict) or document.get("asset", {}).get("version") != "2.0":
        raise ValueError("Modular GLB must declare glTF 2.0.")
    buffers = document.get("buffers", [])
    if len(buffers) != 1 or "uri" in buffers[0]:
        raise ValueError("Modular GLB must use one embedded buffer.")
    binary = chunks[1][1]
    count = _integer(buffers[0].get("byteLength"), "buffer byteLength")
    if not count <= len(binary) <= count + 3:
        raise ValueError("Modular GLB BIN length differs from its declared buffer.")
    return document, binary[:count]


def read_accessor(document, binary, index):
    """Read tightly packed/interleaved, non-sparse scalar/vector/MAT4 accessors."""
    accessors = document.get("accessors", [])
    index = _integer(index, "accessor index")
    if index >= len(accessors):
        raise ValueError("GLB accessor index is out of bounds.")
    accessor = accessors[index]
    if "sparse" in accessor:
        raise ValueError("Sparse modular validation accessors are not supported.")
    kind, component = accessor.get("type"), accessor.get("componentType")
    if kind not in _SIZES or component not in _COMPONENTS:
        raise ValueError("Unsupported modular GLB accessor type.")
    views = document.get("bufferViews", [])
    view_index = _integer(accessor.get("bufferView"), "accessor bufferView")
    if view_index >= len(views):
        raise ValueError("GLB accessor bufferView is out of bounds.")
    view = views[view_index]
    if view.get("buffer", 0) != 0:
        raise ValueError("Modular accessor references an external buffer.")
    offset = _integer(view.get("byteOffset", 0), "bufferView byteOffset")
    length = _integer(view.get("byteLength"), "bufferView byteLength")
    inner = _integer(accessor.get("byteOffset", 0), "accessor byteOffset")
    count = _integer(accessor.get("count"), "accessor count", minimum=1)
    code, width = _COMPONENTS[component]
    columns = _SIZES[kind]
    packed = width * columns
    stride = _integer(view.get("byteStride", packed), "accessor stride", minimum=packed)
    if "byteStride" in view and (stride % 4 or not 4 <= stride <= 252):
        raise ValueError("Modular bufferView byteStride must be four-byte aligned and <= 252.")
    if stride % width or inner % width or (offset + inner) % width:
        raise ValueError("Modular accessor alignment is invalid.")
    if offset + length > len(binary) or inner + stride * (count - 1) + packed > length:
        raise ValueError("Modular accessor exceeds its bufferView.")
    normalized = accessor.get("normalized", False)
    if not isinstance(normalized, bool) or (normalized and component in (5125, 5126)):
        raise ValueError("Invalid normalized modular accessor.")
    record = struct.Struct("<" + code * columns)
    result = []
    for row in range(count):
        values = record.unpack_from(binary, offset + inner + row * stride)
        if normalized:
            maximum = {5120: 127, 5121: 255, 5122: 32767, 5123: 65535}[component]
            values = tuple(max(-1.0, value / maximum) for value in values)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Modular accessor contains non-finite values.")
        result.append(values)
    return tuple(result)


__all__ = ("read_glb", "read_accessor")
