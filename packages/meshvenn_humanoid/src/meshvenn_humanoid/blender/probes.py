from contextlib import contextmanager
import math
import bpy
from mathutils import Matrix, Vector


def evaluated_positions(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        return tuple(tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


@contextmanager
def rotated_bone(rig, name, degrees, axis, *, world_space=False):
    bone = rig.pose.bones[name]
    basis = bone.matrix_basis.copy()
    try:
        direction = Vector(axis)
        if world_space:
            direction = (
                rig.matrix_world.to_3x3() @ bone.matrix.to_3x3()
            ).inverted() @ direction
        bone.matrix_basis = basis @ Matrix.Rotation(
            math.radians(degrees), 4, direction.normalized()
        )
        bpy.context.view_layer.update()
        yield
    finally:
        bone.matrix_basis = basis
        bpy.context.view_layer.update()
