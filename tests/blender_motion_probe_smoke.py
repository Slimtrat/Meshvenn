"""Motion rollback preserves user Action slots, pose and fractional timeline."""
from pathlib import Path
import importlib
import math
import sys
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.blender_motion_smoke import _build_target, _import_package


def main():
    package = _import_package(ROOT)
    context,pipeline,rig,_ = _build_target(package,ROOT/"example/v2/assets/QuaterniusHuman.glb")
    implementation = importlib.import_module(f"{package}.implementations.canonical_motion.implementation")
    retarget = importlib.import_module(f"{package}.implementations.canonical_motion.retarget")
    arm = rig.armature_object
    animation = arm.animation_data_create()
    action = bpy.data.actions.new("User_Action_To_Preserve")
    animation.action = action
    animation.use_nla = True
    bone = arm.pose.bones["upper_arm.L"]
    bone.rotation_mode = "XYZ"
    for frame,angle in ((1,.1),(12,.4)):
        bone.rotation_euler.z = angle
        bone.keyframe_insert(data_path="rotation_euler",frame=frame)
    bpy.context.scene.frame_set(8,subframe=.375)
    bpy.context.view_layer.update()
    saved_slot = animation.action_slot
    saved_bones = [(b,b.rotation_mode,b.matrix_basis.copy()) for b in arm.pose.bones]
    actions,objects = set(bpy.data.actions),set(bpy.data.objects)
    context.metadata["motion_source_path"] = str(ROOT/"example/v2/assets/QuaterniusHuman.glb")
    context.metadata["motion_preserve_pelvis_height"] = True
    original = implementation.bake_retargeted_action
    calls = 0

    def fail_second(*args,**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected second-clip failure")
        return original(*args,**kwargs)

    with patch.object(implementation,"bake_retargeted_action",side_effect=fail_second):
        result = implementation.CanonicalMotionRetargetImplementation().execute(context)
    assert result.failed and "injected second-clip failure" in result.message and calls == 2
    assert not context.has_output(pipeline.PipelineStage.MOTION)
    assert set(bpy.data.actions) == actions and set(bpy.data.objects) == objects
    assert animation.action is action and animation.action_slot == saved_slot and animation.use_nla
    assert bpy.context.scene.frame_current == 8 and bpy.context.scene.frame_subframe == .375
    for bone,mode,basis in saved_bones:
        assert bone.rotation_mode == mode
        assert max(abs(x-y) for a,b in zip(basis,bone.matrix_basis) for x,y in zip(a,b)) < 2e-6
    # Invalid opt-in values fail before imports or target mutation.
    for value in (1, "true", None):
        context.metadata["motion_preserve_pelvis_height"] = value
        probe = implementation.CanonicalMotionRetargetImplementation()
        assert not probe.availability(context).ready
        assert probe.execute(context).failed
        assert set(bpy.data.actions) == actions and set(bpy.data.objects) == objects
    context.metadata["motion_preserve_pelvis_height"] = True
    with patch.object(implementation,"_mesh_height",side_effect=ValueError("injected missing source height")):
        assert implementation.CanonicalMotionRetargetImplementation().execute(context).failed
    assert set(bpy.data.actions) == actions and set(bpy.data.objects) == objects
    assert animation.action is action and animation.action_slot == saved_slot and animation.use_nla
    assert bpy.context.scene.frame_current == 8 and bpy.context.scene.frame_subframe == .375
    for value in (0, -1, math.nan, math.inf, True):
        try:
            retarget.bake_retargeted_action(None,None,None,None,root_bone="root",fps=60,
                                           action_name="invalid",pelvis_height_scale=value)
            raise AssertionError("Invalid pelvis height scale was accepted")
        except ValueError:
            pass
    from scripts.glb_v2_contact_support import _match_probes
    probes = {side: [(sign * x, 0, 0) for x in (.1, .2, .3)]
              for side, sign in (("L", 1), ("R", -1))}
    points = list(reversed(probes["L"] + probes["R"] + [probes["L"][0]]))
    matches = _match_probes(points, probes)
    for side, matched_patch in matches.items():
        for point, indices in zip(probes[side], matched_patch):
            assert indices and all(points[index] == point for index in indices)
    assert len(matches["L"][0]) == 2  # Coincident UV seam, not another probe.
    for damaged in ([point for point in points if point != probes["L"][1]], [(0,0,0)]):
        try:
            _match_probes(damaged, probes)
            raise AssertionError("Lost sole rest position was accepted")
        except AssertionError as error:
            assert "Missing or ambiguous" in str(error)
    # Both legacy and layered Action storage must receive LINEAR interpolation.
    for layered in (False,True):
        point = SimpleNamespace(interpolation="BEZIER")
        curve = SimpleNamespace(keyframe_points=[point])
        candidate = SimpleNamespace(layers=[SimpleNamespace(strips=[SimpleNamespace(
            channelbags=[SimpleNamespace(fcurves=[curve])])])]) if layered else SimpleNamespace(fcurves=[curve])
        retarget._set_linear_interpolation(candidate)
        assert point.interpolation == "LINEAR"
    try:
        retarget._set_linear_interpolation(SimpleNamespace(layers=[]))
        raise AssertionError("Empty baked action was silently accepted")
    except RuntimeError:
        pass
    print("Motion partial-bake rollback, user Action slot/subframe and layered interpolation: PASS")


if __name__ == "__main__":
    main()
