"""Embed resolved modular references in the temporary GLB, never a published file."""

from __future__ import annotations

import json
import struct


MODULAR_EXTRAS_KEY = "meshvenn_modular_character"


def _reference(value, entries, label):
    if type(value) is not int or not 0 <= value < len(entries):
        raise ValueError(f"Invalid modular {label} reference.")
    return value


def embed_modular_metadata(path, spec):
    payload = path.read_bytes()
    if len(payload) < 20:
        raise ValueError("Temporary modular GLB is too small.")
    magic, version, size = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2 or size != len(payload):
        raise ValueError("Invalid temporary modular GLB header.")
    chunks, offset = [], 12
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValueError("Truncated temporary modular GLB chunk header.")
        length, kind = struct.unpack_from("<II", payload, offset)
        offset += 8
        if length % 4 or offset + length > len(payload):
            raise ValueError("Truncated or misaligned temporary modular GLB chunk.")
        chunks.append((kind, payload[offset:offset + length]))
        offset += length
    if offset != size or not chunks or chunks[0][0] != 0x4E4F534A:
        raise ValueError("Invalid temporary modular GLB chunks.")
    document = json.loads(chunks[0][1])
    if MODULAR_EXTRAS_KEY in document.get("asset", {}).get("extras", {}):
        raise ValueError("Temporary GLB already declares a modular contract.")
    nodes = document.get("nodes", [])
    skins = document.get("skins", [])
    meshes = document.get("meshes", [])
    if (not isinstance(nodes, list) or any(not isinstance(node, dict) for node in nodes)
            or not isinstance(meshes, list) or not isinstance(skins, list) or len(skins) != 1):
        raise ValueError("Modular export must contain one unchanged skin and valid nodes/meshes.")
    region_nodes = {}
    skin_indices = set()
    for region in spec.regions:
        matches = [(index, node) for index, node in enumerate(nodes)
                   if node.get("extras", {}).get("meshvenn_region_id") == region.id]
        if len(matches) != 1 or "mesh" not in matches[0][1] or "skin" not in matches[0][1]:
            raise ValueError(f"Region {region.id!r} has no unique exported skinned node.")
        index, node = matches[0]
        if any(other.get("name") == region.node_name and other is not node for other in nodes):
            raise ValueError(f"Region {region.id!r} collides with another exported node name.")
        # Derived preview objects may already use this name in the authoring
        # scene. Resolve by stable ID and name only this temporary GLB node.
        node["name"] = region.node_name
        _reference(node["mesh"], meshes, "mesh")
        _reference(node["skin"], skins, "skin")
        region_nodes[region.id] = index
        skin_indices.add(node["skin"])
    if len(skin_indices) != 1:
        raise ValueError("Modular regions must reference the same original skin.")
    skin_index = skin_indices.pop()
    if type(skin_index) is not int or not 0 <= skin_index < len(skins):
        raise ValueError("Modular region has a dangling skin reference.")
    joints = skins[skin_index].get("joints", [])
    if not isinstance(joints, list) or not joints:
        raise ValueError("Modular skin must retain its native joints.")
    for index in joints:
        _reference(index, nodes, "joint")
    joint_names = {nodes[index].get("name"): index for index in joints}
    if len(joint_names) != len(joints) or any(not isinstance(name, str) or not name for name in joint_names):
        raise ValueError("Modular skin contains ambiguous native joint names.")
    sockets = {}
    for socket in spec.sockets:
        if socket.parent_bone not in joint_names:
            raise ValueError(f"Socket {socket.id!r} lost its native parent bone.")
        sockets[socket.id] = {"parent_joint_node": joint_names[socket.parent_bone],
                              "owner_region_node": region_nodes[socket.region_id]}
    envelope = {"spec": spec.to_dict(), "bindings": {
        "region_nodes": region_nodes, "skin": skin_index,
        "joint_nodes": joint_names, "sockets": sockets}}
    document.setdefault("asset", {}).setdefault("extras", {})[MODULAR_EXTRAS_KEY] = envelope
    encoded = json.dumps(document, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    chunks[0] = (chunks[0][0], encoded)
    body = b"".join(struct.pack("<II", len(data), kind) + data for kind, data in chunks)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, len(body) + 12) + body)
    return envelope
