"""Explicit transactional shoulder rest correction on an authored static source."""
from contextlib import contextmanager
import json

import bpy
from mathutils import Matrix, Vector

from ...core.canonical_rig import BoneSpec
from ...core.rig_owned_skin import ALGORITHM as SKIN_ALGORITHM, ROLES
from ...core.rig_shoulder_alignment import ALGORITHM, plan_shoulder_alignment
from ..glb_export.face_authoring import _surface
from ..glb_export.modular_source import _catalogue


def _validate(mesh, spec):
    if (bpy.context.mode != "OBJECT" or mesh is None or mesh.type != "MESH" or mesh.mode != "OBJECT" or mesh.library
            or mesh.data.library or mesh.data.users != 1 or "meshvenn_source_mesh" in mesh
            or "meshvenn_shoulder_alignment" in mesh
            or mesh.get("meshvenn_rig_skinning_algorithm") != SKIN_ALGORITHM):
        raise ValueError("Select an unaligned, local authored-body-skin authority in Object mode.")
    if (spec.rig_id != "canonical-biped-v2" or set(spec.ownership) != {mesh.name}
            or len(spec.regions) != 5 or {r.role for r in spec.regions} != ROLES
            or spec.ownership_source_sha256[mesh.name] != _surface(mesh)):
        raise ValueError("Require exact authored native source ownership.")
    modifiers = [m for m in mesh.modifiers if m.show_viewport or m.show_render]
    if len(modifiers) != 1 or modifiers[0].type != "ARMATURE" or modifiers[0].object is None:
        raise ValueError("Require one active native armature binding.")
    rig = modifiers[0].object
    if (rig.mode != "OBJECT" or rig.library or rig.data.library or rig.data.users != 1
            or rig.constraints or any(b.constraints for b in rig.pose.bones)
            or rig.get("meshvenn_rig_implementation") != "canonical-biped-v2"):
        raise ValueError("Require a local single-user, unconstrained native rig in Object mode.")
    catalogue = _catalogue((mesh,))
    if catalogue["rig"]["armature"] != rig.name or catalogue["clips"]:
        raise ValueError("Rest correction is static-source authoring; existing animation is never silently migrated.")
    ids = {mesh,rig,mesh.data,rig.data}
    for obj in (mesh,rig):
        parent = obj.parent
        while parent:
            ids.add(parent)
            parent = parent.parent
    if (any(item.animation_data and (item.animation_data.action or item.animation_data.drivers
            or any(t.strips for t in item.animation_data.nla_tracks)) for item in ids)
            or mesh.data.shape_keys is not None
            or any(max(abs(v-expected) for row,identity in zip(b.matrix_basis,Matrix.Identity(4))
                       for v,expected in zip(row,identity)) > 1e-7 for b in rig.pose.bones)):
        raise ValueError("Reset the source pose and remove animation/shape deformation before explicit rest correction.")
    if any(s.parent_bone in {"upper_arm.L","upper_arm.R"} for s in spec.sockets):
        raise ValueError("Sockets directly on moved shoulders require explicit re-authoring; they will not be silently relocated.")
    return rig


def _staged_armature(rig, shifts):
    """Edit a disposable data copy; original rest bytes survive every failure."""
    original = rig.data
    staged = original.copy()
    work = bpy.data.objects.new("MeshvennShoulderAlignment.Work", staged)
    bpy.context.scene.collection.objects.link(work)
    active, selected = bpy.context.view_layer.objects.active, tuple(bpy.context.selected_objects)
    succeeded = False
    try:
        bpy.ops.object.select_all(action="DESELECT")
        work.select_set(True)
        bpy.context.view_layer.objects.active = work
        bpy.ops.object.mode_set(mode="EDIT")
        for name, offset in shifts.items():
            bone = staged.edit_bones[name]
            if bone.use_connect:
                raise ValueError("Connected shoulder editing would move a different native joint.")
            bone.head += Vector(offset)
            bone.tail += Vector(offset)
        bpy.ops.object.mode_set(mode="OBJECT")
        for bone in staged.bones:
            old = original.bones[bone.name]
            if (bone.parent.name if bone.parent else None) != (old.parent.name if old.parent else None):
                raise ValueError("Shoulder editing changed the native hierarchy.")
            if max(abs(a-b) for ra,rb in zip(bone.matrix_local.to_3x3(),old.matrix_local.to_3x3()) for a,b in zip(ra,rb)) > 2e-6:
                raise ValueError("Shoulder editing changed a native joint axis.")
            expected = old.head_local+Vector(shifts.get(bone.name,(0,0,0)))
            if (bone.head_local-expected).length > 2e-5:
                raise ValueError("Shoulder editing changed an undeclared joint origin.")
        succeeded = True
        return staged
    finally:
        if work.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.data.objects.remove(work,do_unlink=True)
        if not succeeded:
            bpy.data.armatures.remove(staged)
        for obj in selected:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = active


@contextmanager
def align_authored_shoulders(mesh, spec):
    """Keep weights and authored socket parent frames; explicit new rest provenance.

    Consumer captures against the old rests require labelled rest-relative
    derivation, NOT direct reuse of their old absolute bone-local matrices.
    On failure the exact original armature datablock and source properties return.
    """
    rig = _validate(mesh,spec)
    to_mesh = mesh.matrix_world.inverted() @ rig.matrix_world
    roles = {r.id:r.role for r in spec.regions}
    bones = [BoneSpec(b.name,b.parent.name if b.parent else None,
        tuple(to_mesh @ b.head_local),tuple(to_mesh @ b.tail_local),b.use_deform) for b in rig.data.bones]
    shifts, report = plan_shoulder_alignment([tuple(v.co) for v in mesh.data.vertices],
        [tuple(p.vertices) for p in mesh.data.polygons],[roles[r] for r in spec.ownership[mesh.name]],bones)
    rig_shifts = {name: tuple(to_mesh.inverted().to_3x3() @ Vector(offset)) for name,offset in shifts.items()}
    staged = _staged_armature(rig,rig_shifts)
    original = rig.data
    report["unchanged_socket_parent_matrix_max_error"] = max(
        (abs(a-b) for socket in spec.sockets
         for ra,rb in zip(original.bones[socket.parent_bone].matrix_local,staged.bones[socket.parent_bone].matrix_local)
         for a,b in zip(ra,rb)),default=0.)
    report["representation_scope"] = "Unedited rest matrices may recalculate float32 caches on entering Edit mode; socket parent error is diagnostic within existing 2e-4 native matrix tolerance."
    properties = ("meshvenn_native_rest_revision","meshvenn_shoulder_alignment")
    saved = {key:mesh[key] for key in properties if key in mesh}
    try:
        rig.data = staged
        mesh[properties[0]] = ALGORITHM
        mesh[properties[1]] = json.dumps(report,sort_keys=True,allow_nan=False)
        bpy.context.view_layer.update()
        yield report
    except BaseException:
        rig.data = original
        for key in properties:
            if key in saved:
                mesh[key] = saved[key]
            elif key in mesh:
                del mesh[key]
        bpy.data.armatures.remove(staged)
        bpy.context.view_layer.update()
        raise
