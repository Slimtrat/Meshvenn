"""Disposable-mesh staging for distal native chain isolation; exact rollback."""
from contextlib import contextmanager
import json

import bpy
from mathutils import Matrix

from ...core.canonical_rig import BoneSpec
from ...core.rig_limb_chain import refine_distal_limb_weights
from ...core.rig_owned_skin import ALGORITHM as PARENT_ALGORITHM, ROLES, DEFORM
from ..glb_export.face_authoring import _surface
from ..glb_export.modular_source import _catalogue


def _validate(mesh,spec):
    if (bpy.context.mode != "OBJECT" or mesh is None or mesh.type != "MESH" or mesh.mode != "OBJECT"
            or mesh.library or mesh.data.library or mesh.data.users != 1 or "meshvenn_source_mesh" in mesh
            or "meshvenn_distal_limb_refinement" in mesh
            or mesh.get("meshvenn_rig_skinning_algorithm") != PARENT_ALGORITHM):
        raise ValueError("Select a local single-user authored-body source without this distal edit, in Object mode.")
    if (spec.rig_id != "canonical-biped-v2" or set(spec.ownership) != {mesh.name}
            or len(spec.regions) != 5 or {r.role for r in spec.regions} != ROLES
            or spec.ownership_source_sha256[mesh.name] != _surface(mesh)):
        raise ValueError("Require the exact authored five-region source surface.")
    active = [m for m in mesh.modifiers if m.show_viewport or m.show_render]
    if len(active) != 1 or active[0].type != "ARMATURE" or active[0].object is None:
        raise ValueError("Require one active native armature binding.")
    rig = active[0].object
    if (rig.mode != "OBJECT" or rig.library or rig.data.library or rig.data.users != 1
            or rig.constraints or any(b.constraints for b in rig.pose.bones)
            or rig.get("meshvenn_rig_implementation") != "canonical-biped-v2"):
        raise ValueError("Require an unshared local unconstrained native rig.")
    catalogue = _catalogue((mesh,))
    if catalogue["rig"]["armature"] != rig.name or catalogue["clips"]:
        raise ValueError("This is explicit static-source authoring, not an animation migration.")
    ids = {mesh,rig,mesh.data,rig.data}
    for obj in (mesh,rig):
        parent = obj.parent
        while parent:
            ids.add(parent); parent = parent.parent
    if (mesh.data.shape_keys is not None
            or any(item.animation_data and (item.animation_data.action or item.animation_data.drivers
                   or any(t.strips for t in item.animation_data.nla_tracks)) for item in ids)
            or any(max(abs(v-i) for row,identity in zip(b.matrix_basis,Matrix.Identity(4))
                       for v,i in zip(row,identity)) > 1e-7 for b in rig.pose.bones)):
        raise ValueError("Remove animation/shape deformation and reset the source pose before this edit.")
    parent_report = json.loads(mesh.get("meshvenn_owned_skin_refinement","null"))
    if not isinstance(parent_report,dict) or parent_report.get("algorithm") != PARENT_ALGORITHM:
        raise ValueError("Require the preceding authored-body collar provenance.")
    return rig,parent_report["collar_in_heights"]


def _stage(mesh,previous,replacement):
    staged,work,completed = mesh.data.copy(),None,False
    try:
        work = mesh.copy(); work.data = staged
        groups = {g.name:g for g in work.vertex_groups}
        for index,(old,new) in enumerate(zip(previous,replacement)):
            if old == new: continue
            for name in old.keys() | new.keys(): groups[name].remove((index,))
            for name,value in new.items(): groups[name].add((index,),value,"REPLACE")
        completed = True
        return staged
    finally:
        if work is not None: bpy.data.objects.remove(work,do_unlink=True)
        if not completed and staged.users == 0: bpy.data.meshes.remove(staged)


@contextmanager
def refine_authored_distal_limbs(mesh,spec):
    """Keep the preceding skin stage and record this explicit successor separately."""
    rig,collar = _validate(mesh,spec)
    names = {g.index:g.name for g in mesh.vertex_groups}
    if any(g.weight > 0 and names[g.group] not in DEFORM for v in mesh.data.vertices for g in v.groups):
        raise ValueError("Unexpected positive non-native weights; no source edit.")
    if any(names[g.group] not in DEFORM | {"root"} for v in mesh.data.vertices for g in v.groups):
        raise ValueError("Keep auxiliary groups separate from native skin authoring.")
    previous = [{names[g.group]:float(g.weight) for g in v.groups} for v in mesh.data.vertices]
    role_by_id = {r.id:r.role for r in spec.regions}
    to_mesh = mesh.matrix_world.inverted() @ rig.matrix_world
    bones = [BoneSpec(b.name,b.parent.name if b.parent else None,
             tuple(to_mesh @ b.head_local),tuple(to_mesh @ b.tail_local),b.use_deform) for b in rig.data.bones]
    replacement,report = refine_distal_limb_weights([tuple(v.co) for v in mesh.data.vertices],
        [tuple(p.vertices) for p in mesh.data.polygons],[role_by_id[r] for r in spec.ownership[mesh.name]],
        previous,bones,collar_in_heights=collar)
    original,staged = mesh.data,_stage(mesh,previous,replacement)
    prop = "meshvenn_distal_limb_refinement"
    try:
        mesh.data = staged
        mesh[prop] = json.dumps(report,sort_keys=True,allow_nan=False)
        bpy.context.view_layer.update()
        yield report
    except BaseException:
        mesh.data = original
        if prop in mesh: del mesh[prop]
        if staged.users == 0: bpy.data.meshes.remove(staged)
        bpy.context.view_layer.update()
        raise
