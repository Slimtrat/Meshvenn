"""Ensure diagnostic rotations restore full Blender pose state on failure."""
from pathlib import Path
import math
import sys

import bpy
from mathutils import Matrix

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.glb_v2_pose_support import rotated_bone
from scripts.glb_v2_combined_metrics import Rotation
from scripts.glb_v2_combined_support import rotated_chain, _sample_reference


def _matrix_error(a,b):
    return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))


def _combined_probes(arm):
    bpy.ops.object.mode_set(mode="EDIT")
    parent = arm.data.edit_bones[0]
    parent.name = "parent"
    parent.roll = .4
    child = arm.data.edit_bones.new("child")
    child.head,child.tail = parent.tail,(.2,0,2)
    child.parent = parent
    child.roll = -.7
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.matrix_world = Matrix.Translation((2,-1,3)) @ Matrix.Rotation(.2,4,"X")
    bones = [arm.pose.bones[name] for name in ("parent","child")]
    for mode in ("XYZ","QUATERNION","AXIS_ANGLE"):
        for bone in bones:
            bone.rotation_mode = mode
            bone.matrix_basis = Matrix.Rotation(.3,4,"Z")
        bpy.context.view_layer.update()
        basis = [bone.matrix_basis.copy() for bone in bones]
        before_world = [arm.matrix_world @ bone.matrix for bone in bones]
        try:
            with rotated_chain(arm,(Rotation("parent","Y",45),Rotation("child","Z",90))):
                actual = [arm.matrix_world @ bone.matrix for bone in bones]
                parent_delta = Matrix.Rotation(math.radians(45),4,"Y")
                child_delta = Matrix.Rotation(math.radians(90),4,"Z")
                expected = [parent_delta @ before_world[0],child_delta @ parent_delta @ before_world[1]]
                for a,b in zip(actual,expected):
                    assert _matrix_error(a.to_3x3(),b.to_3x3()) < 2e-6
                raise RuntimeError("injected combined evaluation failure")
        except RuntimeError as exc:
            assert str(exc) == "injected combined evaluation failure"
        for bone,saved in zip(bones,basis):
            assert bone.rotation_mode == mode and _matrix_error(saved,bone.matrix_basis) < 1e-6
        invalid = ((),(Rotation("parent","Y",45),Rotation("child","W",90)),
                   (Rotation("parent","Y",45),Rotation("missing","Z",90)),
                   (Rotation("parent","Y",45),Rotation("child","Z",math.nan)),
                   (Rotation("child","Z",90),Rotation("parent","Y",45)),
                   (Rotation("parent","Y",45),Rotation("parent","Z",90)))
        for rotations in invalid:
            try:
                with rotated_chain(arm,rotations):
                    raise AssertionError("Invalid chain mutated the pose")
            except ValueError:
                pass
            for bone,saved in zip(bones,basis):
                assert _matrix_error(saved,bone.matrix_basis) < 1e-6


def _reference_samples():
    coarse = [(0,0,0),(.01,0,0),(.02,0,0),(.03,0,0)]
    reference = _sample_reference(coarse,{"joint":(0,0,0)},1)
    assert reference["positions"] == [list(p) for p in coarse]
    assert _sample_reference(coarse[::-1]*3,{"joint":(0,0,0)},1) == reference
    dense = [(i*.001,j*.001,0) for i in range(100) for j in range(10)]
    centers = {str(i):(i*.01,0,0) for i in range(8)}
    assert 16 <= len(_sample_reference(dense,centers,1)["positions"]) <= 80
    for height in (0,math.inf,-1):
        try:
            _sample_reference(coarse,centers,height)
            raise AssertionError("Invalid sample height was accepted")
        except ValueError:
            pass


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
    _combined_probes(arm)
    _reference_samples()
    print("Isolated/combined pose restoration, parent-first world axes and bounded samples: PASS")


if __name__ == "__main__":
    main()
