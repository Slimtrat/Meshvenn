"""Preserve source seam normals without Blender's regional fan quantization."""

from __future__ import annotations

import json
import struct

from .modular_gltf import read_accessor, read_glb
from .modular_partition import COLOR_SEMANTIC_PREFIX, NORMAL_SEMANTIC, REGION_ID_KEY


def restore_modular_normals(path):
    """Use the source float32 normal transport as standard glTF NORMAL.

    This changes only a temporary, unpublished GLB's accessor references. The
    float32 data is not inferred from rounded regional custom normals. Unused
    old NORMAL storage is harmless and retained to avoid rebasing other views.
    """
    document, binary = read_glb(path)
    restored = 0
    for node in document.get("nodes", []):
        if REGION_ID_KEY not in node.get("extras", {}) or "mesh" not in node:
            continue
        for primitive in document["meshes"][node["mesh"]].get("primitives", []):
            attributes = primitive.get("attributes", {})
            if NORMAL_SEMANTIC not in attributes or "TANGENT" in attributes:
                raise ValueError("Modular normals require source transport and no uncertified tangents.")
            index = attributes[NORMAL_SEMANTIC]
            accessor = document["accessors"][index]
            if accessor.get("type") != "VEC3" or accessor.get("componentType") != 5126 or accessor.get("normalized", False):
                raise ValueError("Modular source normal transport must be an unquantized float32 VEC3.")
            values = read_accessor(document, binary, index)
            positions = read_accessor(document, binary, attributes.get("POSITION"))
            if len(values) != len(positions) or any(abs(sum(v * v for v in normal) - 1) > 2e-6 for normal in values):
                raise ValueError("Modular source normal transport is not unit length or vertex aligned.")
            attributes["NORMAL"] = attributes.pop(NORMAL_SEMANTIC)
            if any(semantic.startswith(COLOR_SEMANTIC_PREFIX) for semantic in attributes):
                # Transport layers themselves are also visible to Blender's
                # "all colors" option. Discard its possibly whitened/duplicate
                # COLOR channels before publishing the exact source channels.
                for semantic in tuple(attributes):
                    if semantic.startswith("COLOR_"):
                        del attributes[semantic]
            for semantic in tuple(attributes):
                if not semantic.startswith(COLOR_SEMANTIC_PREFIX):
                    continue
                color_index = semantic.removeprefix(COLOR_SEMANTIC_PREFIX)
                if not color_index.isdigit():
                    raise ValueError("Invalid modular source color transport channel.")
                color_accessor = document["accessors"][attributes[semantic]]
                if color_accessor.get("type") != "VEC4" or color_accessor.get("componentType") != 5126:
                    raise ValueError("Modular source color transport must be unquantized linear float32 VEC4.")
                color_values = read_accessor(document, binary, attributes[semantic])
                if len(color_values) != len(positions):
                    raise ValueError("Modular source color transport differs from its vertex count.")
                attributes[f"COLOR_{color_index}"] = attributes.pop(semantic)
            restored += 1
    if not restored:
        raise ValueError("Modular GLB contains no source-normal transport primitives.")
    encoded = json.dumps(document, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    padded_binary = binary + b"\0" * (-len(binary) % 4)
    body = (struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(padded_binary), 0x004E4942) + padded_binary)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, len(body) + 12) + body)
    return restored


__all__ = ("restore_modular_normals",)
