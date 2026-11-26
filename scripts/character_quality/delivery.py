"""Inspect the exact downloaded GLB; reuse the existing strict binary reader."""
from __future__ import annotations

from functools import lru_cache
import hashlib
from pathlib import Path
import runpy

from scripts.diagnostic_qualification.integrity import native_path, sha256_file

ROOT = Path(__file__).resolve().parents[2]
READER = ROOT / "implementations/glb_export/modular_gltf.py"


@lru_cache(maxsize=1)
def _reader():
    digest = sha256_file(READER)
    functions = runpy.run_path(str(READER), run_name="character_quality_glb_reader")
    if sha256_file(READER) != digest:
        raise ValueError("The authoritative GLB reader changed while loading.")
    return functions, digest


def inspect_delivery(path: Path, expected_sha256: str, *, max_bytes=64*1024*1024,
                     max_vertices=500_000, max_triangles=300_000) -> dict:
    """Resource and triangle-definition checks; not a style or animation certificate."""
    path = native_path(path)
    if path.is_symlink() or not path.is_file() or not 20 <= path.stat().st_size <= max_bytes:
        raise ValueError("GLB must be a bounded regular file.")
    before = sha256_file(path)
    if before != expected_sha256:
        raise ValueError("The delivered GLB does not match the reviewed artifact hash.")
    functions, reader_sha = _reader()
    if sha256_file(READER) != reader_sha:
        raise ValueError("The cached GLB reader is stale.")
    document, binary = functions["read_glb"](path)
    for image in document.get("images", []):
        if "uri" in image:
            raise ValueError("This profile requires texture resources in embedded GLB buffer views.")
        view = image.get("bufferView")
        if type(view) is not int or not 0 <= view < len(document.get("bufferViews", [])):
            raise ValueError("Embedded GLB image has no valid buffer view.")
    for view in document.get("bufferViews", []):
        offset, length = view.get("byteOffset", 0), view.get("byteLength")
        if (view.get("buffer", 0) != 0 or type(offset) is not int or type(length) is not int
                or offset < 0 or length < 0 or offset + length > len(binary)):
            raise ValueError("GLB resource range escapes its embedded buffer.")
    total_vertices = total_triangles = 0
    read_accessor = functions["read_accessor"]
    definitions = []
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if primitive.get("mode", 4) != 4:
                raise ValueError("Character review currently supports triangle primitives only.")
            position = primitive.get("attributes", {}).get("POSITION")
            if type(position) is not int or not 0 <= position < len(document.get("accessors", [])):
                raise ValueError("GLB triangle primitive has no valid position accessor.")
            accessor = document["accessors"][position]
            count = accessor.get("count")
            if type(count) is not int or not 0 < count <= max_vertices - total_vertices:
                raise ValueError("GLB vertex definition budget exceeded.")
            if accessor.get("type") != "VEC3":
                raise ValueError("GLB vertex positions must have three coordinates.")
            vertices = read_accessor(document, binary, position)
            indices = primitive.get("indices")
            if indices is None:
                index_count = len(vertices)
            else:
                if type(indices) is not int or not 0 <= indices < len(document["accessors"]):
                    raise ValueError("GLB index accessor is invalid.")
                definition = document["accessors"][indices]
                index_count = definition.get("count")
                if (definition.get("type") != "SCALAR" or definition.get("componentType") not in (5121, 5123, 5125)
                        or type(index_count) is not int or not 0 < index_count <= 3 * (max_triangles - total_triangles)):
                    raise ValueError("GLB triangle index definition is unsupported or over budget.")
                values = read_accessor(document, binary, indices)
                if any(type(row[0]) is not int or not 0 <= row[0] < len(vertices) for row in values):
                    raise ValueError("GLB triangle index is outside its actual positions.")
            if index_count % 3 or index_count // 3 > max_triangles - total_triangles:
                raise ValueError("GLB triangle definition budget or alignment is invalid.")
            total_vertices += len(vertices)
            total_triangles += index_count // 3
            definitions.append({"vertices": len(vertices), "triangles": index_count // 3})
    if not definitions or total_triangles == 0:
        raise ValueError("GLB has no character triangle surface.")
    after = sha256_file(path)
    if after != before:
        raise ValueError("The GLB changed during inspection.")
    return {"schema_version": 1, "integrity_status": "verified", "glb_sha256": before,
            "bytes": path.stat().st_size, "mesh_definitions": len(document["meshes"]),
            "vertex_definition_count": total_vertices, "triangle_definition_count": total_triangles,
            "primitives": definitions, "embedded_binary_sha256": hashlib.sha256(binary).hexdigest(),
            "external_resources": 0, "skins": len(document.get("skins", [])),
            "animations": len(document.get("animations", [])), "reader_sha256": reader_sha,
            "reader_path": READER.relative_to(ROOT).as_posix(),
            "limits": {"bytes": max_bytes, "vertex_definitions": max_vertices, "triangle_definitions": max_triangles},
            "fresh_blender_reload": "unknown", "visual_quality": "unknown", "animated_use": "unknown",
            "limitation": "Definition counts are not transformed scene-instance counts; Blender reload/render evidence is separate."}
