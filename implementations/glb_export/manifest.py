"""Minimal GLB integrity and manifest inspection for exported artifacts."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GLB_MAGIC = b"glTF"
GLB_VERSION = 2
JSON_CHUNK_TYPE = 0x4E4F534A


@dataclass(frozen=True)
class GLBManifest:
    path: Path
    size_bytes: int
    sha256: str
    version: int
    node_names: tuple[str, ...]
    animation_names: tuple[str, ...]
    scene_count: int
    mesh_count: int
    skin_count: int
    material_count: int


def _named_entries(
    document: dict[str, Any],
    key: str,
    *,
    require_unique: bool = False,
) -> tuple[str, ...]:
    entries = document.get(key, [])
    if not isinstance(entries, list):
        raise ValueError(f'GLB JSON member "{key}" must be an array.')
    names = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f'GLB JSON member "{key}" contains an invalid entry.')
        value = str(entry.get("name", "")).strip() or f"{key[:-1].title()}_{index}"
        names.append(value)
    if require_unique and len(names) != len(set(names)):
        raise ValueError(f'GLB JSON member "{key}" contains duplicate names.')
    return tuple(names)


def _array_count(document: dict[str, Any], key: str) -> int:
    value = document.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f'GLB JSON member "{key}" must be an array.')
    return len(value)


def inspect_glb(
    path: str | Path,
    *,
    require_unique_animation_names: bool = True,
) -> GLBManifest:
    artifact_path = Path(path).expanduser().resolve(strict=True)
    size_bytes = artifact_path.stat().st_size
    if size_bytes < 20:
        raise ValueError("GLB artifact is too small to contain a JSON chunk.")

    payload = artifact_path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", payload, 0)
    if magic != GLB_MAGIC:
        raise ValueError("Exported artifact does not have the GLB magic header.")
    if version != GLB_VERSION:
        raise ValueError(f"Unsupported GLB version: {version}.")
    if declared_length != len(payload):
        raise ValueError(
            f"GLB declared length {declared_length} does not match {len(payload)} bytes."
        )

    offset = 12
    json_payload: bytes | None = None
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise ValueError("GLB contains a truncated chunk header.")
        chunk_length, chunk_type = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunk_end = offset + chunk_length
        if chunk_end > len(payload):
            raise ValueError("GLB contains a truncated chunk payload.")
        if chunk_type == JSON_CHUNK_TYPE and json_payload is None:
            json_payload = payload[offset:chunk_end]
        offset = chunk_end
    if offset != len(payload) or json_payload is None:
        raise ValueError("GLB artifact does not contain a valid JSON chunk.")

    try:
        document = json.loads(json_payload.rstrip(b" \t\r\n\0").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("GLB JSON chunk is invalid.") from exc
    if not isinstance(document, dict):
        raise ValueError("GLB JSON root must be an object.")
    asset = document.get("asset")
    if not isinstance(asset, dict) or str(asset.get("version", "")) != "2.0":
        raise ValueError("GLB asset metadata must declare glTF 2.0.")

    return GLBManifest(
        path=artifact_path,
        size_bytes=size_bytes,
        sha256=hashlib.sha256(payload).hexdigest(),
        version=version,
        node_names=_named_entries(document, "nodes"),
        animation_names=_named_entries(
            document,
            "animations",
            require_unique=require_unique_animation_names,
        ),
        scene_count=_array_count(document, "scenes"),
        mesh_count=_array_count(document, "meshes"),
        skin_count=_array_count(document, "skins"),
        material_count=_array_count(document, "materials"),
    )


__all__ = ("GLBManifest", "inspect_glb")
