"""Private process adapter calling the existing native surface mesh engine."""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

from .core.geometry_contracts import GeometryProjectionSpace
from .core.geometry_diagnostics import VolumeArtifact
from .core.native_bridge import NativeCore
from .errors import EngineError
from .native import MAX_EXPOSED_FACES, MAX_MESH_INDICES, MAX_MESH_JSON_BYTES, MAX_MESH_VERTICES


def _surface_budget(volume):
    """Bound an existing engine call by the exposed-cell surface capacity."""
    size, raw, faces = volume.width, volume.values, 0
    plane = size * size
    for index, value in enumerate(raw):
        if not value:
            continue
        z, rest = divmod(index, plane)
        y, x = divmod(rest, size)
        for neighbor, inside in ((index-1, x>0), (index+1, x+1<size),
                (index-size, y>0), (index+size, y+1<size), (index-plane, z>0), (index+plane, z+1<size)):
            faces += not inside or not raw[neighbor]
        if faces > MAX_EXPOSED_FACES:
            raise EngineError("resource_limit", "Occupied cell surface exceeds the native mesh output budget.")


def main(arguments=None):
    source, target = map(Path, sys.argv[1:] if arguments is None else arguments)
    started = time.monotonic()
    try:
        if source.stat().st_size > 2_000_000:
            raise EngineError("resource_limit", "Native mesh request exceeds its protocol budget.")
        request = json.loads(source.read_text(encoding="utf-8"))
        volume = VolumeArtifact.from_dict(request["volume"])
        library = Path(request["library_path"])
        if hashlib.sha256(library.read_bytes()).hexdigest() != request["library_sha256"]:
            raise EngineError("native_failure", "Native library changed before isolated mesh execution.")
        _surface_budget(volume)
        mesh = NativeCore(library).build_surface_mesh(volume.as_native(), voxel_size=request["voxel_size"],
            center_xy=request["center_xy"], mesh_mode=request["mesh_mode"])
        if mesh.vertex_count > MAX_MESH_VERTICES or mesh.index_count > MAX_MESH_INDICES:
            raise EngineError("resource_limit", "Native mesh exceeds its vertex/index output budget.")
        vertices, indices = list(mesh.vertices), list(mesh.indices)
        starts, sizes = list(mesh.polygon_starts), list(mesh.polygon_sizes)
        cursor = 0
        if len(starts) != len(sizes) or any(not math.isfinite(v) for v in vertices):
            raise EngineError("native_failure", "Native mesh has invalid finite geometry data.")
        for start, size in zip(starts, sizes):
            if start != cursor or size < 3:
                raise EngineError("native_failure", "Native mesh has invalid polygon ranges.")
            cursor += size
        if cursor != len(indices) or any(not 0 <= i < mesh.vertex_count for i in indices):
            raise EngineError("native_failure", "Native mesh has invalid vertex indices.")
        space = GeometryProjectionSpace(volume.width, volume.depth, volume.height,
                                        request["voxel_size"], request["center_xy"])
        result = {"schema_version": 1, "verification_status": "unknown",
            "mesh": {"vertices": vertices, "indices": indices, "polygon_starts": starts,
                "polygon_sizes": sizes, "vertex_count": mesh.vertex_count, "polygon_count": mesh.polygon_count},
            "projection_space": {"width": space.width, "depth": space.depth, "height": space.height,
                "voxel_size": space.voxel_size, "center_xy": space.center_xy, "convention": space.convention.value},
            "provenance": {"native_abi": 1, "native_library_sha256": request["library_sha256"],
                "source_volume_sha256": volume.sha256, "mesh_mode": request["mesh_mode"],
                "isolation": "subprocess", "worker_pid": os.getpid(), "elapsed_seconds": time.monotonic()-started},
            "limitations": ["Technical surface extraction does not certify hidden shape, topology, appearance or export."]}
        response = {"ok": True, "result": result}
    except EngineError as exc:
        response = {"ok": False, "error": exc.to_dict()}
    except Exception as exc:
        response = {"ok": False, "error": {"code": "native_failure", "message": f"{type(exc).__name__}: {exc}", "details": {}}}
    encoded = json.dumps(response, allow_nan=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_MESH_JSON_BYTES:
        encoded = json.dumps({"ok": False, "error": {"code": "resource_limit", "message": "Native mesh output exceeds 32 MiB."}}).encode()
    temporary = target.with_suffix(".pending")
    temporary.write_bytes(encoded)
    temporary.replace(target)


if __name__ == "__main__":
    main()
