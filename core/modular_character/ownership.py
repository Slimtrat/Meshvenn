"""Source-surface fingerprints and explicit face-ownership validation."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping
from types import MappingProxyType

from .validation import identifier, integer, sequence, sha256, text, vector


def normalize_ownership(value):
    if not isinstance(value, Mapping) or not value:
        raise ValueError("ownership must declare every nonempty source mesh.")
    result = {}
    for name, owners in value.items():
        text(name, name="ownership source object")
        normalized = tuple(identifier(owner, name="face region id")
                           for owner in sequence(owners, name=f"ownership[{name}]"))
        if not normalized:
            raise ValueError(f"ownership[{name}] cannot be empty.")
        result[name] = normalized
    return MappingProxyType(dict(sorted(result.items())))


def normalize_hashes(value, *, source_names):
    if not isinstance(value, Mapping) or set(value) != set(source_names):
        raise ValueError("Source fingerprints must cover exactly the ownership source objects.")
    return MappingProxyType({name: sha256(value[name], name=f"source fingerprint {name}")
                             for name in sorted(value)})


def validate_ownership(ownership, region_ids):
    sources = {}
    for source, owners in ownership.items():
        for owner in owners:
            if owner not in region_ids:
                raise ValueError(f"Unknown face region {owner!r} in {source!r}.")
            previous = sources.setdefault(owner, source)
            if previous != source:
                raise ValueError(f"Region {owner!r} spans multiple source meshes, unsupported in v1.")
    unused = set(region_ids) - set(sources)
    if unused:
        raise ValueError(f"Declared regions have no source faces: {sorted(unused)}.")


def validate_source_surfaces(ownership, fingerprints, mesh_face_counts, mesh_surface_hashes):
    if not isinstance(mesh_face_counts, Mapping) or set(mesh_face_counts) != set(ownership):
        raise ValueError("Face counts must cover exactly every ownership source object.")
    hashes = normalize_hashes(mesh_surface_hashes, source_names=ownership)
    for source, owners in ownership.items():
        count = integer(mesh_face_counts[source], name=f"face count {source}", minimum=1)
        if len(owners) != count:
            raise ValueError(f"Incomplete ownership for {source!r}: {len(owners)} owners for {count} polygons.")
        if hashes[source] != fingerprints[source]:
            raise ValueError(f"Stale ownership: source surface fingerprint changed for {source!r}.")


def validated_polygons(polygons, *, vertex_count):
    integer(vertex_count, name="vertex_count", minimum=1)
    faces = sequence(polygons, name="polygons")
    if not faces:
        raise ValueError("A source surface must contain polygons.")
    result = []
    for index, polygon in enumerate(faces):
        vertices = tuple(integer(item, name=f"polygon {index} vertex")
                         for item in sequence(polygon, name=f"polygon {index}"))
        if len(vertices) < 3 or len(set(vertices)) != len(vertices):
            raise ValueError(f"Polygon {index} must have at least three distinct vertex indices.")
        if any(item >= vertex_count for item in vertices):
            raise ValueError(f"Polygon {index} references an unknown vertex.")
        result.append(vertices)
    return tuple(result)


def mesh_surface_sha256(vertices, polygons):
    """Fingerprint ordered float64 positions and ordered uint64 polygons, not weights.

    The wire representation is little-endian and version tagged. A vertex or face
    reorder invalidates authoring ownership even when counts remain identical.
    """
    positions = tuple(vector(vertex, 3, name="source vertex")
                      for vertex in sequence(vertices, name="vertices"))
    faces = validated_polygons(polygons, vertex_count=len(positions))
    digest = hashlib.sha256(b"meshvenn.surface-fingerprint-v1\0")
    digest.update(struct.pack("<QQ", len(positions), len(faces)))
    for position in positions:
        # Treat signed zero as the same geometric coordinate.
        digest.update(struct.pack("<ddd", *(value if value else 0.0 for value in position)))
    for face in faces:
        digest.update(struct.pack("<Q", len(face)))
        digest.update(struct.pack(f"<{len(face)}Q", *face))
    return digest.hexdigest()
