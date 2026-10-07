"""Observed source attachment centers, not a new rig or anatomy classifier."""
from __future__ import annotations

import math

from .canonical_rig import bounds_from_vertices
from .modular_character import partition_faces
from .rig_owned_skin import DEFORM, ROLES
from .native_pose_probe import PARENTS

ALGORITHM = "authored-closed-shoulder-rings-v1"
SHOULDERS = {"left-arm": "upper_arm.L", "right-arm": "upper_arm.R"}


def observed_shoulder_centers(vertices, polygons, roles):
    """Require one closed manifold cut ring per explicitly authored arm.

    Length-weighted ring centers are independent of face order, UV splits and
    subdivision of a straight boundary edge. The source itself is never welded.
    Only the existing upright, Z-up five-region authored biped is supported.
    """
    points = tuple(tuple(p) for p in vertices)
    if not points or any(len(p) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in points):
        raise ValueError("Require a finite unchanged source surface.")
    bounds = bounds_from_vertices(points)
    faces, roles = tuple(tuple(f) for f in polygons), tuple(roles)
    partition_faces(faces, roles, sorted(ROLES), vertex_count=len(points))
    if {i for f in faces for i in f} != set(range(len(points))):
        raise ValueError("Unused source vertices cannot define attachment bounds.")
    origin, height = bounds.minimum, bounds.height
    normalized = [tuple((v-o)/height for v,o in zip(p, origin)) for p in points]
    keys = [tuple(round(v, 8) for v in p) for p in normalized]
    positions, edges = {}, {}
    for key, p in zip(keys, normalized):
        positions[key] = min(positions.get(key, p), p)
    for face, role in zip(faces, roles):
        welded = [keys[i] for i in face]
        if len(set(welded)) != len(welded):
            raise ValueError("Degenerate source face cannot define an attachment ring.")
        for a,b in zip(welded, (*welded[1:], welded[0])):
            edges.setdefault(tuple(sorted((a,b))), []).append(role)
    if any(len(owners) != 2 for owners in edges.values()):
        raise ValueError("Shoulder alignment requires a closed manifold source, not an open scan.")
    centers, evidence = {}, {}
    for role, name in SHOULDERS.items():
        boundary = [edge for edge, owners in edges.items() if set(owners) == {"body-core", role}]
        graph = {}
        for a,b in boundary:
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)
        if len(graph) < 3 or any(len(neighbors) != 2 for neighbors in graph.values()):
            raise ValueError(f"Require one unambiguous closed attachment ring for {role}.")
        start = min(graph)
        ring, previous, current = [], None, start
        while current not in ring:
            ring.append(current)
            following = min(graph[current]-({previous} if previous is not None else set()))
            previous, current = current, following
        if current != start or set(ring) != set(graph):
            raise ValueError(f"Disconnected attachment rings for {role}; no pivot was inferred.")
        segments = [(positions[a], positions[b]) for a,b in sorted(boundary)]
        lengths = [math.dist(a,b) for a,b in segments]
        perimeter = sum(lengths)
        center = tuple(sum((a[i]+b[i])*.5*l for (a,b),l in zip(segments,lengths))/perimeter for i in range(3))
        normal = [sum((positions[a][(i+1)%3]-positions[b][(i+1)%3])
                       *(positions[a][(i+2)%3]+positions[b][(i+2)%3])
                       for a,b in zip(ring, (*ring[1:],ring[0]))) for i in range(3)]
        area = math.sqrt(sum(v*v for v in normal))
        if area < 1e-5:
            raise ValueError("A degenerate attachment ring cannot locate an articulated pivot.")
        planarity = max(abs(sum((positions[k][i]-center[i])*normal[i]/area for i in range(3))) for k in ring)
        radius = max(math.dist(positions[k],center) for k in ring)
        native = tuple(o+height*v for o,v in zip(origin,center))
        lateral = (native[0]-bounds.center_x)/height
        if (planarity > .025 or not .01 < radius < .12 or not .5 < center[2] < .75
                or not .04 < (lateral if role == "left-arm" else -lateral) < .35):
            raise ValueError("Attachment ring is not an observed upright biped shoulder.")
        centers[name] = native
        evidence[name] = {"role": role, "ring_vertex_count": len(ring), "center": list(native),
                          "perimeter_in_heights": perimeter, "planarity_error_in_heights": planarity}
    return centers, evidence


def plan_shoulder_alignment(vertices, polygons, roles, bones):
    centers, rings = observed_shoulder_centers(vertices, polygons, roles)
    bones = tuple(bones)
    by_name = {b.name: b for b in bones}
    if (set(by_name) != DEFORM | {"root"} or len(by_name) != len(bones)
            or any(b.parent != PARENTS[b.name] or b.deform != (b.name != "root") for b in bones)):
        raise ValueError("Require the exact eighteen native canonical joints.")
    height = bounds_from_vertices(vertices).height
    shifts = {name: tuple(c-a for c,a in zip(center,by_name[name].head)) for name,center in centers.items()}
    if any(not 1e-5 < math.sqrt(sum(v*v for v in shift))/height < .25 for shift in shifts.values()):
        raise ValueError("Shoulder is already aligned or too far from its observed attachment.")
    return shifts, {"algorithm": ALGORITHM, "observed_rings": rings,
                    "offsets": {name: list(shift) for name,shift in shifts.items()},
                    "changed_native_rest_origins": sorted(shifts),
                    "native_names_parents_and_axes_preserved": True,
                    "scope": "Intentional two-shoulder rest-origin correction; no surface/weight edit or consumer acceptance."}
