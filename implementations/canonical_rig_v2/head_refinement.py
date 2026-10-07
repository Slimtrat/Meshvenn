"""Explicit transactional head-weight refinement of an existing canonical source."""
from __future__ import annotations

import json
import math

from ...core.canonical_rig import bounds_from_vertices
from ...core.rig_head_envelope import ALGORITHM, isolate_head_weights, observe_head_envelope


def refine_head_weights(mesh):
    """Update only weights/provenance; preserve topology, materials and rest rig.

    No fitting/rebuild or animation discovery. Reject derived partition previews,
    linked/multi-user/edit-mode meshes and noncanonical/incomplete bindings.
    All calculation precedes writes; application failure restores exact weights.
    """
    if (mesh is None or mesh.type != "MESH" or mesh.mode != "OBJECT" or mesh.library
            or mesh.data.library or mesh.data.users != 1 or "meshvenn_source_mesh" in mesh):
        raise ValueError("Select a local single-user authoritative mesh in Object mode, not a region preview.")
    if mesh.get("meshvenn_rig_implementation") != "canonical-biped-v2":
        raise ValueError("Head refinement requires an existing Canonical Biped V2 source.")
    if (mesh.get("meshvenn_rig_skinning_algorithm") == ALGORITHM
            or "meshvenn_owned_skin_refinement" in mesh):
        raise ValueError("This source already uses head isolation; rebind explicitly instead of repeatedly transferring weights.")
    active = [m for m in mesh.modifiers if m.show_viewport or m.show_render]
    if len(active) != 1 or active[0].type != "ARMATURE" or active[0].object is None:
        raise ValueError("Head refinement requires exactly one native armature binding.")
    rig = active[0].object
    required = {"root", "pelvis", "spine", "chest", "neck", "head",
                *(f"{part}.{side}" for side in ("L", "R")
                  for part in ("upper_arm", "forearm", "hand", "thigh", "shin", "foot"))}
    if (rig.library or rig.data.library or rig.get("meshvenn_rig_implementation") != "canonical-biped-v2"
            or set(rig.data.bones.keys()) != required or not rig.data.bones["head"].use_deform
            or any(b.use_deform != (b.name != "root") for b in rig.data.bones)):
        raise ValueError("Head refinement requires the exact eighteen-joint native canonical rig.")
    deform = required-{"root"}
    groups = {g.name: g for g in mesh.vertex_groups}
    if not deform <= groups.keys():
        raise ValueError("Missing native deform groups; no weights were changed.")
    by_index = {g.index: g.name for g in mesh.vertex_groups}
    vertices = [tuple(v.co) for v in mesh.data.vertices]
    bounds = bounds_from_vertices(vertices)
    mesh.data.calc_loop_triangles()
    envelope = observe_head_envelope(vertices, [tuple(t.vertices) for t in mesh.data.loop_triangles], bounds)
    if envelope is None:
        raise ValueError("No persistent closed neck narrowing observed; existing weights are left unchanged.")
    previous, replacement = [], []
    for vertex in mesh.data.vertices:
        native = {by_index[g.group]: float(g.weight) for g in vertex.groups if by_index[g.group] in deform}
        if any(not math.isfinite(v) or v <= 0 for v in native.values()):
            raise ValueError("Invalid native weights; no weights were changed.")
        previous.append(native)
        replacement.append(isolate_head_weights(native, vertex.co.z, envelope))
    changed = [i for i, (a, b) in enumerate(zip(previous, replacement)) if a != b]
    properties = ("meshvenn_rig_skinning_algorithm", "meshvenn_head_isolation")
    saved = {key: mesh[key] for key in properties if key in mesh}
    report = {"algorithm": ALGORITHM, "envelope": envelope.as_dict(), "changed_vertex_count": len(changed),
              "vertex_count": len(vertices), "native_rest_joints_unchanged": True,
              "scope": "Intentional head weights edit; geometry, UVs, atlas and lower-body weights unchanged."}

    def apply(rows):
        for i in changed:
            for name in set(previous[i]) | set(replacement[i]):
                groups[name].remove((i,))
            for name, value in rows[i].items():
                groups[name].add((i,), value, "REPLACE")

    try:
        apply(replacement)
        mesh[properties[0]] = ALGORITHM
        mesh[properties[1]] = json.dumps(report, sort_keys=True, allow_nan=False)
    except Exception:
        apply(previous)
        for key in properties:
            if key in saved:
                mesh[key] = saved[key]
            elif key in mesh:
                del mesh[key]
        raise
    return report
