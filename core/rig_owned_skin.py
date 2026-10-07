"""Explicit authored-region skin refinement; never infer anatomical ownership.

The body uses adjacent axial anchors and an observed head envelope. Only local
surface collars share a limb root; distal limb weights remain bit-for-bit intact.
Distances are discrete edge geodesics, not Euclidean proximity to another limb.
This does not refit joints, introduce animation, or qualify artistic appearance.
"""
from __future__ import annotations

import heapq
import math

from .canonical_rig import bounds_from_vertices
from .modular_character import partition_faces
from .rig_head_envelope import HeadEnvelope, isolate_head_weights

ALGORITHM = "authored-regional-v1-axial-isolation"
LIMB_ROOTS = {"left-arm": "upper_arm.L", "right-arm": "upper_arm.R",
              "left-leg": "thigh.L", "right-leg": "thigh.R"}
ROLES = frozenset(("body-core", *LIMB_ROOTS))
DEFORM = frozenset(("pelvis", "spine", "chest", "neck", "head",
                    *(f"{part}.{side}" for side in ("L", "R")
                      for part in ("upper_arm", "forearm", "hand", "thigh", "shin", "foot"))))
COLLAR_IN_HEIGHTS = .06


def _smooth(start, end, value):
    t = max(0., min(1., (value-start)/(end-start)))
    return t*t*(3-2*t)


def _bounded(values):
    # Match the selected source to the exporter before transport; its strict
    # normal and weight fidelity tolerances are unchanged.
    kept = sorted(((k, v) for k, v in values.items() if v > 1.01e-4),
                  key=lambda item: (-item[1], item[0]))[:4]
    total = sum(v for _, v in kept)
    return {k: v/total for k, v in kept}


def _surface_distances(points, polygons, roles, height):
    """Weld coincident seams only for observation; never mutate the mesh."""
    origin = tuple(min(p[i] for p in points) for i in range(3))
    normalized = [tuple((v-o)/height for v, o in zip(p, origin)) for p in points]
    keys = [tuple(round(v, 8) for v in p) for p in normalized]
    positions, members, graph = {}, {}, {}
    for key, p in zip(keys, normalized):
        positions[key] = min(positions.get(key, p), p)
        members.setdefault(key, set())
        graph.setdefault(key, {})
    for face, role in zip(polygons, roles):
        welded = [keys[i] for i in face]
        if len(set(welded)) != len(welded):
            raise ValueError("Degenerate welded face cannot define a skin collar.")
        for key in welded:
            members[key].add(role)
        for a, b in zip(welded, (*welded[1:], welded[0])):
            graph[a][b] = graph[b][a] = math.dist(positions[a], positions[b])
    if any(not m or (len(m) > 1 and (len(m) != 2 or "body-core" not in m)) for m in members.values()):
        raise ValueError("Require unambiguous body-to-limb interfaces and no unused vertices.")
    distances, counts = {}, {}
    for limb in LIMB_ROOTS:
        boundary = [k for k, m in members.items() if m == {"body-core", limb}]
        if len(boundary) < 3:
            raise ValueError(f"Missing connected source interface for {limb}.")
        boundary_set, seen, pending = set(boundary), set(), [boundary[0]]
        while pending:
            a = pending.pop()
            if a not in seen:
                seen.add(a)
                pending.extend(b for b in graph[a] if b in boundary_set and b not in seen)
        if seen != boundary_set:
            raise ValueError(f"Disconnected source interface for {limb}; attachment ownership is ambiguous.")
        allowed = {k for k, m in members.items() if m & {"body-core", limb}}
        distance = {k: math.inf for k in allowed}
        queue = []
        for k in boundary:
            distance[k] = 0.
            heapq.heappush(queue, (0., k))
        while queue:
            value, a = heapq.heappop(queue)
            if value != distance[a]:
                continue
            for b, length in sorted(graph[a].items()):
                if b in allowed and value+length < distance[b]:
                    distance[b] = value+length
                    heapq.heappush(queue, (value+length, b))
        if any(not math.isfinite(v) for v in distance.values()):
            raise ValueError("Disconnected authored region cannot define a skin collar.")
        distances[limb] = distance
        counts[limb] = len(boundary)
    return keys, members, distances, counts


def refine_owned_weights(vertices, polygons, roles, weights, bones, envelope,
                         *, collar_in_heights=COLLAR_IN_HEIGHTS):
    """Plan a complete deterministic edit without any Blender or source writes.

    Roles are explicit source face declarations, not geometry classifications.
    The head observation is mandatory; absent/ambiguous anatomy rejects the edit.
    Four normalized native influences maximum, same values at welded interfaces,
    and exact old weights beyond two collar widths inside each limb.
    """
    if (not isinstance(envelope, HeadEnvelope) or type(collar_in_heights) not in (int, float)
            or not math.isfinite(collar_in_heights) or not .02 <= collar_in_heights <= .08):
        raise ValueError("Require an observed head envelope and a collar in [0.02, 0.08] heights.")
    points = [tuple(p) for p in vertices]
    if (not points or len(points) != len(weights)
            or any(len(p) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in points)):
        raise ValueError("Expected unchanged finite vertices and matching native weights.")
    bounds = bounds_from_vertices(points)
    polygons, roles = tuple(tuple(f) for f in polygons), tuple(roles)
    partition_faces(polygons, roles, sorted(ROLES), vertex_count=len(points))
    bones = tuple(bones)
    deform = {b.name: b for b in bones if b.deform}
    if set(deform) != DEFORM or len(deform) != sum(b.deform for b in bones):
        raise ValueError("Require the exact native canonical deform chains.")
    anchors = [deform[name].head[2] for name in ("pelvis", "spine", "chest")]
    if not anchors[0] < anchors[1] < anchors[2] or not bounds.minimum[2] < envelope.start_z < envelope.end_z < bounds.maximum[2]:
        raise ValueError("Nonupright axial anchors or out-of-surface head evidence.")
    for row in weights:
        if (not isinstance(row, dict) or not row or len(row) > 4 or not set(row) <= DEFORM
                or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in row.values())
                or not math.isclose(sum(row.values()), 1., abs_tol=1e-6)):
            raise ValueError("Invalid normalized native weights; no edit was planned.")
    keys, members, distances, counts = _surface_distances(points, polygons, roles, bounds.height)
    old_by_key = {}
    for key, row in zip(keys, weights):
        old = old_by_key.setdefault(key, row)
        if any(abs(old.get(k, 0)-row.get(k, 0)) > 1e-6 for k in old.keys() | row.keys()):
            raise ValueError("Coincident source seam has contradictory skin weights.")

    def axial(z):
        if z <= anchors[0]:
            result = {"pelvis": 1.}
        elif z <= anchors[1]:
            t = _smooth(anchors[0], anchors[1], z)
            result = _bounded({"pelvis": 1-t, "spine": t})
        else:
            t = _smooth(anchors[1], anchors[2], z)
            result = _bounded({"spine": 1-t, "chest": t})
        return isolate_head_weights(result, z, envelope)

    result, unchanged_distal = [], 0
    for p, key, old in zip(points, keys, weights):
        target = axial(p[2])
        if "body-core" in members[key]:
            roots = {root: .5*(1-_smooth(0, collar_in_heights, distances[limb][key]))
                     for limb, root in LIMB_ROOTS.items()}
            mass = sum(roots.values())
            if mass > 1.+1e-8:
                raise ValueError("Overlapping authored attachment collars are ambiguous.")
            values = {k: v*(1-min(1., mass)) for k, v in target.items()}
            values.update(roots)
        else:
            limb = next(iter(members[key]))
            d = distances[limb][key]
            if d >= 2*collar_in_heights:
                result.append(dict(old))
                unchanged_distal += 1
                continue
            fade = _smooth(collar_in_heights, 2*collar_in_heights, d)
            root_mass = .5+.5*_smooth(0, collar_in_heights, d)
            values = {k: target.get(k, 0)*(1-root_mass)*(1-fade)+old.get(k, 0)*fade
                      for k in target.keys() | old.keys()}
            root = LIMB_ROOTS[limb]
            values[root] = values.get(root, 0)+root_mass*(1-fade)
        result.append(_bounded(values))
    return result, {"algorithm": ALGORITHM, "collar_in_heights": collar_in_heights,
                    "distance_policy": "source polygon-edge geodesics; coincident seams welded for observation only",
                    "interface_vertex_counts": counts, "head_envelope": envelope.as_dict(),
                    "unchanged_distal_vertex_count": unchanged_distal,
                    "changed_vertex_count": sum(a != b for a, b in zip(weights, result)),
                    "native_rest_joints_unchanged": True,
                    "scope": "Intentional authored axial/attachment weight edit; no joint refit or full visual acceptance."}
