"""Read-only Blender replay of captured Godot native-local transforms."""
import bpy
from mathutils import Matrix

AXES = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))


def accumulated(probe, *, rest=False):
    result = {}
    for bone in probe.ordered():
        local = Matrix(bone.rest if rest else bone.pose)
        result[bone.name] = result[bone.parent] @ local if bone.parent else local
    return result


def matrix_error(a, b):
    return max(abs(x-y) for ra, rb in zip(a, b) for x,y in zip(ra, rb))


def native_deltas(probe):
    rest, pose = accumulated(probe, rest=True), accumulated(probe)
    # The exporter changes the WORLD frame (left multiply A), not each bone's
    # local basis. Compose captured parent-local matrices BEFORE conjugation.
    return {name: AXES.inverted() @ pose[name] @ rest[name].inverted() @ AXES for name in rest}


def apply_probe(rig, probe):
    if set(rig.data.bones.keys()) != {b.name for b in probe.bones}:
        raise ValueError("Probe joint names do not match this native armature.")
    for captured in probe.bones:
        bone = rig.data.bones[captured.name]
        if (bone.parent.name if bone.parent else None) != captured.parent:
            raise ValueError("Probe hierarchy does not match this native armature.")
    rig.data.pose_position = "POSE"
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    bpy.context.view_layer.update()
    deltas = native_deltas(probe)
    for captured in probe.ordered():
        bone = rig.pose.bones[captured.name]
        bone.matrix = deltas[bone.name] @ bone.bone.matrix_local
        bpy.context.view_layer.update()
    applied_error = max(matrix_error(rig.pose.bones[name].matrix @ rig.data.bones[name].matrix_local.inverted(), delta)
                        for name, delta in deltas.items())
    if applied_error > 2e-4:
        raise ValueError(f"Blender could not reproduce the captured affine pose ({applied_error}).")
    return applied_error
