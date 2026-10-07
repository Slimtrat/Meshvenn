"""Transactional authored-region refinement of an existing native source."""
from __future__ import annotations

import json

from ...core.canonical_rig import BoneSpec, bounds_from_vertices
from ...core.rig_head_envelope import observe_head_envelope
from ...core.rig_owned_skin import ALGORITHM, DEFORM, ROLES, refine_owned_weights
from ..glb_export.face_authoring import _surface


def refine_owned_skin(mesh, spec):
    """Explicit source edit; geometry, ownership, textures and rest rig survive."""
    if (mesh is None or mesh.type != "MESH" or mesh.mode != "OBJECT" or mesh.library
            or mesh.data.library or mesh.data.users != 1 or "meshvenn_source_mesh" in mesh):
        raise ValueError("Select a local single-user authoritative mesh in Object mode.")
    if (mesh.get("meshvenn_rig_implementation") != "canonical-biped-v2"
            or spec.rig_id != "canonical-biped-v2" or mesh.get("meshvenn_rig_skinning_algorithm") == ALGORITHM
            or "meshvenn_owned_skin_refinement" in mesh):
        raise ValueError("Require an existing canonical source that has not already received this edit.")
    if (set(spec.ownership) != {mesh.name} or spec.ownership_source_sha256[mesh.name] != _surface(mesh)
            or len(spec.ownership[mesh.name]) != len(mesh.data.polygons)):
        raise ValueError("Authored ownership must match the exact authoritative source surface.")
    role_by_id = {r.id: r.role for r in spec.regions}
    if len(role_by_id) != 5 or set(role_by_id.values()) != ROLES:
        raise ValueError("Declare one body-core and four limb roles explicitly; no ownership is guessed.")
    active = [m for m in mesh.modifiers if m.show_viewport or m.show_render]
    if len(active) != 1 or active[0].type != "ARMATURE" or active[0].object is None:
        raise ValueError("Require exactly one active native armature binding.")
    rig = active[0].object
    if (rig.library or rig.data.library or rig.get("meshvenn_rig_implementation") != "canonical-biped-v2"
            or set(rig.data.bones.keys()) != DEFORM | {"root"}
            or any(b.use_deform != (b.name != "root") for b in rig.data.bones)):
        raise ValueError("Require the unchanged eighteen-joint canonical native rig.")
    groups = {g.name: g for g in mesh.vertex_groups}
    if not DEFORM <= groups.keys():
        raise ValueError("Missing native deform groups; weights are unchanged.")
    names = {g.index: g.name for g in mesh.vertex_groups}
    if any(g.weight > 0 and names[g.group] not in DEFORM
           for v in mesh.data.vertices for g in v.groups):
        raise ValueError("Unexpected positive non-native skin weights; no edit was applied.")
    previous = [{names[g.group]: float(g.weight) for g in v.groups if names[g.group] in DEFORM}
                for v in mesh.data.vertices]
    vertices = [tuple(v.co) for v in mesh.data.vertices]
    mesh.data.calc_loop_triangles()
    envelope = observe_head_envelope(vertices, [tuple(t.vertices) for t in mesh.data.loop_triangles],
                                     bounds_from_vertices(vertices))
    if envelope is None:
        raise ValueError("No persistent neck surface cue; this upright biped edit is not applicable.")
    to_mesh = mesh.matrix_world.inverted() @ rig.matrix_world
    bones = [BoneSpec(b.name, b.parent.name if b.parent else None,
                      tuple(to_mesh @ b.head_local), tuple(to_mesh @ b.tail_local), b.use_deform)
             for b in rig.data.bones]
    replacement, report = refine_owned_weights(vertices, [tuple(p.vertices) for p in mesh.data.polygons],
        [role_by_id[r] for r in spec.ownership[mesh.name]], previous, bones, envelope)
    changed = [i for i, (a, b) in enumerate(zip(previous, replacement)) if a != b]
    properties = ("meshvenn_rig_skinning_algorithm", "meshvenn_owned_skin_refinement")
    saved = {key: mesh[key] for key in properties if key in mesh}

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
