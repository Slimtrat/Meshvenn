"""Bounded, topology-preserving anti-terracing for native Surface Nets.

This removes voxel-scale noise; it neither infers anatomy nor creates detail.
Open/non-manifold boundaries and degenerate faces are pinned. Closed components
retain their signed volume within 2%; triangle orientation and area are checked.
Global self-intersection freedom is not certified by these local checks.
"""
from __future__ import annotations

import math
from array import array
from dataclasses import replace

from .native_bridge.models import NativeMesh
from .surface_safety import constrain_faces, _normal, _dot

REFINEMENT_PAIRS = 24
CONTOUR_REFINEMENT_PAIRS = 48


def validate_surface_refinement(mode: str, mesh_mode: str) -> None:
    if mode not in ("none", "organic"):
        raise ValueError("Surface refinement must be none or organic.")
    if mode == "organic" and mesh_mode != "surface_nets":
        raise ValueError("Organic refinement requires Surface Nets, not voxel blocks.")


def _volume(points, triangles, origin):
    # Component-local origin avoids cancellation for translated meshes.
    return math.fsum(_dot(tuple(points[t[0]][k]-origin[k] for k in range(3)),
                          _normal(points, t)) / 6 for t in triangles)


def _roughness(points, neighbors, voxel_size):
    values = [math.dist(p, tuple(math.fsum(points[j][k] for j in row)/len(row)
                                for k in range(3)))
              for p, row in zip(points, neighbors) if row]
    return math.fsum(values)/max(1, len(values))/voxel_size


def refine_native_surface(mesh: NativeMesh, *, voxel_size: float,
                          mode: str = "none", mesh_mode: str = "surface_nets",
                          contour_surface=None) -> tuple[NativeMesh, dict]:
    validate_surface_refinement(mode, mesh_mode)
    if not math.isfinite(voxel_size) or voxel_size <= 0:
        raise ValueError("Refinement voxel size must be finite and positive.")
    if mode == "none":
        return mesh, {"mode": "none", "applied": False}
    if contour_surface is not None and not math.isclose(
            contour_surface.space.voxel_size, voxel_size, rel_tol=1e-12, abs_tol=0):
        raise ValueError("Contour and mesh voxel sizes must match.")
    if (not mesh.vertex_count or len(mesh.vertices) % 3
            or len(mesh.polygon_starts) != mesh.polygon_count or not mesh.polygon_count):
        raise ValueError("Organic refinement requires a valid nonempty mesh.")
    original = [tuple(mesh.vertices[i:i+3]) for i in range(0, len(mesh.vertices), 3)]
    if any(not math.isfinite(x) for p in original for x in p):
        raise ValueError("Surface vertices must be finite.")
    neighbors = [set() for _ in original]
    edges, triangles, pinned = {}, [], set()
    cursor = 0
    for start, size in zip(mesh.polygon_starts, mesh.polygon_sizes):
        if start != cursor or size < 3 or start+size > mesh.index_count:
            raise ValueError("Invalid surface polygon buffers.")
        face = tuple(mesh.indices[start:start+size])
        if any(i < 0 or i >= len(original) for i in face) or len(set(face)) != len(face):
            raise ValueError("Invalid surface polygon indices.")
        cursor += size
        for a, b in zip(face, face[1:]+face[:1]):
            neighbors[a].add(b)
            neighbors[b].add(a)
            edge = tuple(sorted((a, b)))
            edges[edge] = edges.get(edge, 0)+1
        for i in range(1, size-1):
            tri = (face[0], face[i], face[i+1])
            triangles.append(tri)
            if _dot(_normal(original, tri), _normal(original, tri)) <= voxel_size**4 * 1e-20:
                pinned.update(face)
    if cursor != mesh.index_count:
        raise ValueError("Unused surface polygon indices.")
    for edge, count in edges.items():
        if count != 2:
            pinned.update(edge)
    neighbors = [tuple(sorted(row)) for row in neighbors]
    # Components are constrained independently: a large torso must not mask
    # excessive volume loss in a small hand or accessory.
    components, membership = [], [-1]*len(original)
    for start in range(len(original)):
        if membership[start] != -1:
            continue
        index, pending, component = len(components), [start], []
        membership[start] = index
        while pending:
            vertex = pending.pop()
            component.append(vertex)
            for other in neighbors[vertex]:
                if membership[other] == -1:
                    membership[other] = index
                    pending.append(other)
        components.append(component)
    component_triangles = [[] for _ in components]
    for tri in triangles:
        component_triangles[membership[tri[0]]].append(tri)
    points = original
    limit = .75 * voxel_size
    if contour_surface is not None:
        points = [p if i in pinned else contour_surface.project(p,p,limit)
                  for i,p in enumerate(original)]
    pairs = CONTOUR_REFINEMENT_PAIRS if contour_surface is not None else REFINEMENT_PAIRS
    for _ in range(pairs):
        for strength in (.5, -.5 if contour_surface is not None else -.53):
            proposed = []
            for i, (p, row) in enumerate(zip(points, neighbors)):
                if i in pinned or not row:
                    proposed.append(original[i])
                    continue
                q = tuple(p[k]+strength*(math.fsum(points[j][k] for j in row)/len(row)-p[k])
                          for k in range(3))
                distance = math.dist(q, original[i])
                if distance > limit:
                    q = tuple(original[i][k]+(q[k]-original[i][k])*limit/distance for k in range(3))
                proposed.append(q)
            points = proposed
    locally_limited = 0
    if contour_surface is not None:
        # Keep most of the anti-terracing pass rather than restoring every
        # pixel-scale corner of the signed-distance field in the final fit.
        fitted = [p if i in pinned else contour_surface.project(p,original[i],limit,iterations=3)
                  for i,p in enumerate(points)]
        points = [tuple(.75*p[k]+.25*q[k] for k in range(3)) for p,q in zip(points,fitted)]
        points, locally_limited = constrain_faces(original,points,triangles,limit)
    volume_drifts, attenuated = [], 0
    for component, tris in zip(components, component_triangles):
        normals = [_normal(original, t) for t in tris]
        origin = original[component[0]]
        closed = all(edges[tuple(sorted((a,b)))] == 2
                     for t in tris for a,b in zip(t,t[1:]+t[:1])
                     if tuple(sorted((a,b))) in edges)
        initial_volume = _volume(original, tris, origin)
        volume_checked = closed and abs(initial_volume) > voxel_size**3*1e-12
        candidate = [points[i] for i in component]
        for attempt in range(25):
            factor = 2.0**(-attempt) if attempt < 24 else 0.0
            for i, p in zip(component, candidate):
                # Validate the exact float32 coordinates that Blender receives.
                points[i] = tuple(array("f", (original[i][k]+factor*(p[k]-original[i][k])
                                             for k in range(3))))
            valid_faces = all(_dot(_normal(points,t), n) >= .1*_dot(n,n)
                              for t,n in zip(tris,normals))
            within_bound = all(math.dist(points[i], original[i]) <= limit for i in component)
            drift = abs(_volume(points,tris,origin)/initial_volume-1) if volume_checked else 0.0
            if valid_faces and within_bound and drift <= .02:
                if attempt:
                    attenuated += 1
                if volume_checked:
                    volume_drifts.append(drift)
                break
        else:
            raise ValueError("Surface refinement could not preserve face orientation.")
    displacement = max(math.dist(a,b) for a,b in zip(points,original))
    report = {
        "mode": mode,
        "algorithm": "contour-taubin-v2" if contour_surface is not None else "bounded-taubin-v1",
        "applied": displacement > 0,
        "iterations": pairs, "displacement_limit_in_voxels": .75,
        "maximum_displacement_in_voxels": displacement/voxel_size,
        "roughness_before_in_voxels": _roughness(original,neighbors,voxel_size),
        "roughness_after_in_voxels": _roughness(points,neighbors,voxel_size),
        "pinned_vertex_count": len(pinned), "component_count": len(components),
        "volume_checked_component_count": len(volume_drifts),
        "maximum_component_volume_drift": max(volume_drifts) if volume_drifts else None,
        "attenuated_component_count": attenuated, "topology_preserved": True,
        "face_orientation_preserved": True,
    }
    if contour_surface is not None:
        report["locally_limited_vertex_count"] = locally_limited
        before = contour_surface.residual_summary(original)
        after = contour_surface.residual_summary(points)
        report["mean_contour_residual_before_in_voxels"] = before["mean_in_voxels"]
        report["mean_contour_residual_after_in_voxels"] = after["mean_in_voxels"]
        report["contour_residual_sample_count"] = before["total_samples"]
        report["contour_residual_valid_samples_before"] = before["valid_samples"]
        report["contour_residual_valid_samples_after"] = after["valid_samples"]
    return replace(mesh, vertices=array("f", (x for p in points for x in p))), report
