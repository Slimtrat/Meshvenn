"""IK mid-solve rollback, opt-in guards and duplicate split-mesh sole patches."""
from pathlib import Path
import importlib
import sys
from unittest.mock import patch

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.blender_motion_smoke import _build_target, _import_package


def main():
    package = _import_package(ROOT)
    context,pipeline,rig,mesh = _build_target(package,ROOT/"example/v2/assets/QuaterniusHuman.glb")
    module = importlib.import_module(f"{package}.implementations.canonical_motion.implementation")
    ik = importlib.import_module(f"{package}.implementations.canonical_motion.contact_ik")
    surfaces = importlib.import_module(f"{package}.implementations.canonical_motion.contact_surface")
    arm = rig.armature_object
    animation = arm.animation_data_create()
    old_action = bpy.data.actions.new("User_Contact_IK_Action")
    animation.action = old_action
    animation.use_nla = True
    bone = arm.pose.bones["upper_arm.L"]
    bone.rotation_mode = "XYZ"
    for frame,angle in ((1,.1),(12,.3)):
        bone.rotation_euler.z = angle
        bone.keyframe_insert(data_path="rotation_euler",frame=frame)
    bpy.context.scene.frame_set(6,subframe=.25)
    bpy.context.view_layer.update()
    slot = animation.action_slot
    bases = [(bone,bone.rotation_mode,bone.matrix_basis.copy()) for bone in arm.pose.bones]
    data = module.snapshot_blender_data()
    context.metadata.update(motion_source_path=str(ROOT/"example/v2/assets/QuaterniusHuman.glb"),
                            motion_preserve_pelvis_height=True,motion_contact_ik=True)
    calls = 0
    original = ik._move_ankle

    def fail_after_real_solve(*args,**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2: raise RuntimeError("injected mid-IK failure")
        return original(*args,**kwargs)

    with patch.object(ik,"_move_ankle",side_effect=fail_after_real_solve):
        result = module.CanonicalMotionRetargetImplementation().execute(context)
    assert result.failed and "injected mid-IK failure" in result.message and calls == 2
    assert module.snapshot_blender_data() == data
    assert animation.action is old_action and animation.action_slot == slot and animation.use_nla
    assert bpy.context.scene.frame_current == 6 and bpy.context.scene.frame_subframe == .25
    assert not context.has_output(pipeline.PipelineStage.MOTION)
    for bone,mode,basis in bases:
        assert bone.rotation_mode == mode
        assert max(abs(x-y) for a,b in zip(basis,bone.matrix_basis) for x,y in zip(a,b)) < 2e-6
    probe = module.CanonicalMotionRetargetImplementation()
    for invalid in (None,1,"true"):
        context.metadata["motion_contact_ik"] = invalid
        assert not probe.availability(context).ready and probe.execute(context).failed
        assert module.snapshot_blender_data() == data
    context.metadata.update(motion_contact_ik=True,motion_preserve_pelvis_height=False)
    assert not probe.availability(context).ready and "requires" in probe.execute(context).message
    context.metadata["motion_preserve_pelvis_height"] = True
    world = arm.matrix_world.copy()
    arm.matrix_world = Matrix.Diagonal((1.,2.,1.,1.))
    assert not probe.availability(context).ready and probe.execute(context).failed
    arm.matrix_world = world
    constraint = arm.pose.bones["shin.L"].constraints.new("IK")
    assert not probe.availability(context).ready
    arm.pose.bones["shin.L"].constraints.remove(constraint)
    shin = arm.data.bones["shin.L"]
    shin.use_inherit_rotation = False
    assert not probe.availability(context).ready
    shin.use_inherit_rotation = True
    shin.inherit_scale = "NONE"
    assert not probe.availability(context).ready
    shin.inherit_scale = "FULL"
    arm.driver_add("location",0)
    assert not probe.availability(context).ready
    arm.driver_remove("location",0)
    # Linked copies duplicate every seam position across meshes; patches and
    # observed centroids must not double their weight or change their floor.
    copy = mesh.copy()
    bpy.context.scene.collection.objects.link(copy)
    try:
        one = surfaces.SoleSurface((mesh,),arm,rig.semantic_bones,target=True)
        two = surfaces.SoleSurface((mesh,copy),arm,rig.semantic_bones,target=True)
        assert {s:len(p) for s,p in one.patches.items()} == {s:len(p) for s,p in two.patches.items()}
        assert one.observe() == two.observe()
        modifier = mesh.modifiers.new("TestTopologyChange","SUBSURF")
        try:
            try: one.observe()
            except ValueError as exc: assert "topology" in str(exc)
            else: raise AssertionError("Topology-changing modifier accepted")
        finally:
            mesh.modifiers.remove(modifier)
        with patch.object(module,"SoleSurface",side_effect=ValueError("injected missing sole patch")):
            assert probe.execute(context).failed
        # The linked duplicate is intentional; all imported temporary data
        # must still be removed after failing source preparation.
        after = module.snapshot_blender_data()
        assert after.actions == data.actions and after.armatures == data.armatures
        assert after.objects == data.objects | {copy}
    finally:
        bpy.data.objects.remove(copy,do_unlink=True)
    assert module.snapshot_blender_data() == data
    print("Contact IK mid-solve rollback, guards, split-mesh/seam patches: PASS")


if __name__ == "__main__": main()
