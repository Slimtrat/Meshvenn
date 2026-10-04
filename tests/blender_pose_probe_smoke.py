"""Ensure diagnostic rotations restore full Blender pose state on failure."""
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.glb_v2_pose_support import rotated_bone


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.object.armature_add()
    arm = bpy.context.object
    bone = arm.pose.bones[0]
    for mode in ("XYZ","QUATERNION","AXIS_ANGLE"):
        bone.rotation_mode = mode
        bone.matrix_basis = Matrix.Translation((.1,.2,.3)) @ Matrix.Rotation(.3,4,"Z")
        before = bone.matrix_basis.copy()
        bpy.context.view_layer.update()
        for world_space in (False,True):
            try:
                with rotated_bone(arm,bone.name,60,(0,1,0),world_space=world_space):
                    assert any(abs(a-b) > .1 for ra,rb in zip(before,bone.matrix_basis) for a,b in zip(ra,rb))
                    raise RuntimeError("injected evaluation failure")
            except RuntimeError as exc:
                assert str(exc) == "injected evaluation failure"
            assert bone.rotation_mode == mode
            assert max(abs(a-b) for ra,rb in zip(before,bone.matrix_basis) for a,b in zip(ra,rb)) < 1e-6
    # Local bone rolls must not change the meaning of a world-axis probe.
    bone.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    before_world = arm.matrix_world @ bone.matrix
    with rotated_bone(arm,bone.name,60,(0,0,1),world_space=True):
        after_world = arm.matrix_world @ bone.matrix
        expected = Matrix.Rotation(1.0471975511965976,4,"Z") @ before_world
        assert max(abs(a-b) for ra,rb in zip(expected.to_3x3(),after_world.to_3x3()) for a,b in zip(ra,rb)) < 1e-6
    print("Pose probe full-state restoration and world-axis rotation: PASS")


if __name__ == "__main__":
    main()
