"""Immutable declared normalized surfaces; no physical-truth certification."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..diagnostic_contracts import ArtifactReference
from ..diagnostic_contracts.codec import JsonContract, fingerprint, require_sha256, require_version, validate_model

MAX_VERTICES = 65_536
MAX_TRIANGLES = 65_536


@dataclass(frozen=True)
class SurfaceMesh(JsonContract):
    """Declared triangle surface in the native normalized [-1,+1] cube.

    Triangle order and winding are preserved. Provenance names the source
    artifact; a caller may bind the declaration to upstream diagnostic evidence.
    Neither a mesh nor its content hash establishes anatomical or physical truth.
    """
    vertices: tuple[tuple[float, float, float], ...]
    triangles: tuple[tuple[int, int, int], ...]
    provenance: ArtifactReference
    binding_sha256: str | None = None
    schema_version: int = 1

    def __post_init__(self):
        if (type(self.vertices) not in (list, tuple) or not 3 <= len(self.vertices) <= MAX_VERTICES
                or type(self.triangles) not in (list, tuple) or not 1 <= len(self.triangles) <= MAX_TRIANGLES):
            raise ValueError("Surface vertex/triangle counts exceed the normalized surface profile.")
        validate_model(self)
        require_version(self.schema_version)
        if self.binding_sha256 is not None:
            require_sha256(self.binding_sha256, "surface binding_sha256")
        if any(not -1 <= coordinate <= 1 for vertex in self.vertices for coordinate in vertex):
            raise ValueError("Surface vertices must be finite normalized coordinates inside [-1,+1].")
        for triangle in self.triangles:
            if len(set(triangle)) != 3 or any(not 0 <= index < len(self.vertices) for index in triangle):
                raise ValueError("Surface triangle indices must name three distinct existing vertices.")
            a, b, c = (self.vertices[index] for index in triangle)
            e, f = tuple(b[i]-a[i] for i in range(3)), tuple(c[i]-a[i] for i in range(3))
            cross = (e[1]*f[2]-e[2]*f[1], e[2]*f[0]-e[0]*f[2], e[0]*f[1]-e[1]*f[0])
            if math.hypot(*cross) <= 1e-15:
                raise ValueError("Degenerate or numerically unresolved surface triangles are unsupported.")

    @classmethod
    def from_dict(cls, data):
        if (type(data) is not dict or type(data.get("vertices")) is not list
                or type(data.get("triangles")) is not list
                or len(data["vertices"]) > MAX_VERTICES or len(data["triangles"]) > MAX_TRIANGLES):
            raise ValueError("Surface JSON requires bounded vertex and triangle arrays.")
        return super().from_dict(data)

    @property
    def sha256(self) -> str:
        # Geometric content identity is independent of retrieval URI/provenance
        # metadata. Root analysis binds those dependencies separately.
        return fingerprint({"schema_version": self.schema_version,
            "coordinate_space": "native-normalized-cube-v1",
            "vertices": self.vertices, "triangles": self.triangles})
