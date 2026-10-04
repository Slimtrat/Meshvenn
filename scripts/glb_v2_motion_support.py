"""Blender observations for authored-GLB to generated-rig Motion fidelity."""
from __future__ import annotations

import importlib
import math
from pathlib import Path

import bpy
from mathutils import Matrix

from scripts.benchmark_rig_v2 import (
    REPO_ROOT, EXPECTED_BONES, _package_modules, _source_limb_regions, _prepare_unrigged_input,
)
from scripts.glb_v2_motion_metrics import sample_frames
from scripts.glb_v2_contact_support import source_sole_probes, observe_surfaces


def _bind_action(armature, action):
    animation = armature.animation_data_create()
    animation.use_nla = False
    animation.action = None
    for bone in armature.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
    animation.action = action
    armature.data.pose_position = "POSE"


def observe_clip(armature, action, roles, *, name, start, end, fps, height, root):
    """Reference deltas are observed independently of the retarget functions."""
    _bind_action(armature,action)
    samples = []
    for frame in sample_frames(start,end):
        integer = math.floor(frame)
        bpy.context.scene.frame_set(integer,subframe=frame-integer)
        bpy.context.view_layer.update()
        deltas = {}
        for role,bone_name in roles.items():
            rest = (armature.matrix_world @ armature.data.bones[bone_name].matrix_local).to_quaternion()
            pose = (armature.matrix_world @ armature.pose.bones[bone_name].matrix).to_quaternion()
            deltas[role] = list(pose @ rest.inverted())
        position = armature.matrix_world @ armature.pose.bones[root].head
        rest_position = armature.matrix_world @ armature.data.bones[root].head_local
        pelvis = armature.matrix_world @ armature.pose.bones[roles["pelvis"]].head
        pelvis_rest = armature.matrix_world @ armature.data.bones[roles["pelvis"]].head_local
        samples.append({"frame":frame, "rotations":deltas,
                        "root_offset_in_heights":[v/height for v in position-rest_position],
                        "pelvis_height_offset_in_heights":(pelvis.z-pelvis_rest.z)/height})
    return {"name":name, "frame_start":start, "frame_end":end, "fps":fps, "samples":samples}


def prepare_target(path: Path, output: Path, *, observe_contacts=False):
    _,pipeline,rig_module = _package_modules("canonical-biped-v2")
    package = REPO_ROOT.name
    source_module = importlib.import_module(f"{package}.implementations.canonical_motion.source")
    mapping = importlib.import_module(f"{package}.implementations.canonical_motion.mapping")
    imported = source_module.import_external_motion(path,source_module.snapshot_blender_data())
    source = imported.armature
    roles = dict(mapping.resolve_source_profile(source.data.bones.keys()).role_to_bone)
    meshes = [obj for obj in imported.imported_objects if obj.type == "MESH" and any(
        modifier.type == "ARMATURE" and modifier.object is source for modifier in obj.modifiers)]
    mesh = max(meshes,key=lambda obj:len(obj.data.vertices))
    source_z = [float((obj.matrix_world @ v.co).z) for obj in meshes for v in obj.data.vertices]
    source_height = max(source_z)-min(source_z)
    fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    reference = {"clips":[observe_clip(source,action,roles,name=action.name,
                                       start=math.floor(action.frame_range[0]),end=math.ceil(action.frame_range[1]),
                                       fps=fps,height=source_height,root=roles["pelvis"])
                           for action in imported.actions]}
    source.animation_data.action = None
    source.animation_data.use_nla = False
    source.data.pose_position = "REST"
    bpy.context.scene.frame_set(0)
    bpy.context.view_layer.update()
    if observe_contacts:
        probes = source_sole_probes(mesh, source, roles)
        clips = [{"name": action.name, "action": action, "fps": fps,
                  "frame_start": math.floor(action.frame_range[0]),
                  "frame_end": math.ceil(action.frame_range[1])} for action in imported.actions]
        reference["contacts"] = observe_surfaces(mesh, source, clips, probes, _bind_action)
        source.animation_data.action = None
        source.data.pose_position = "REST"
        bpy.context.view_layer.update()
    heads = {bone.name:tuple(source.matrix_world @ bone.head_local) for bone in source.data.bones}
    labels = _source_limb_regions(mesh,source,roles)
    context,mesh,_,_,neutral = _prepare_unrigged_input(mesh,heads,labels,output,pipeline)
    result = rig_module.CanonicalRigV2Implementation().execute(context)
    if not result.success:
        raise AssertionError(result.message)
    rig = result.payload
    context.set_output(pipeline.PipelineStage.RIG,rig)
    height = max(v.co.z for v in mesh.data.vertices)-min(v.co.z for v in mesh.data.vertices)
    return context,pipeline,rig,reference,height,imported.profile.identifier,neutral


def observe_target(rig, motion, reference, height, *, imported_actions=None, armature=None, mesh=None, surface_step=1):
    armature = armature or rig.armature_object
    roles = {role:name for role,name in rig.semantic_bones.items() if role != "root"}
    originals = {clip["name"]:clip for clip in reference["clips"]}
    if {clip.name for clip in motion.clips} != originals.keys():
        raise AssertionError("Retargeting lost a source clip")
    clips = []
    for clip in motion.clips:
        original = originals[clip.name]
        if (clip.frame_start,clip.frame_end,clip.fps) != (
            original["frame_start"],original["frame_end"],original["fps"]):
            raise AssertionError(f"Retargeting changed source timing: {clip.name}")
        action = imported_actions[clip.name] if imported_actions is not None else clip.action
        clips.append(observe_clip(armature,action,roles,name=clip.name,start=clip.frame_start,
                                  end=clip.frame_end,fps=clip.fps,height=height,root=rig.semantic_bones["root"]))
    result = {"clips": clips}
    if "contacts" in reference:
        surface_clips = [{"name": clip.name, "frame_start": clip.frame_start, "frame_end": clip.frame_end,
                          "fps": clip.fps, "action": imported_actions[clip.name] if imported_actions is not None
                          else clip.action} for clip in motion.clips]
        result["contacts"] = observe_surfaces(mesh or rig.blender_object, armature, surface_clips,
                                             reference["contacts"]["probes"], _bind_action, step=surface_step)
    return result


def observe_export(path, rig, motion, reference, height, *, surface_step=1):
    objects = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path),bone_heuristic="TEMPERANCE")
    imported = tuple(obj for obj in bpy.data.objects if obj not in objects)
    arms = [obj for obj in imported if obj.type == "ARMATURE"]
    if len(arms) != 1 or set(arms[0].data.bones.keys()) != EXPECTED_BONES:
        raise AssertionError("Motion GLB changed the canonical skeleton")
    bound = [obj for obj in imported if obj.type == "MESH" and any(
        modifier.type == "ARMATURE" and modifier.object is arms[0] for modifier in obj.modifiers)]
    if len(bound) != 1:
        raise AssertionError("Motion GLB lost its skin")
    tracks = {track.name:track for track in arms[0].animation_data.nla_tracks}
    if len(tracks) != len(motion.clips):
        raise AssertionError("Motion GLB changed the number of clips")
    actions = {}
    for clip in motion.clips:
        track = tracks.get(clip.action.name)
        if track is None or len(track.strips) != 1 or track.strips[0].action is None:
            raise AssertionError(f"Motion GLB lost clip: {clip.name}")
        actions[clip.name] = track.strips[0].action
    return observe_target(rig,motion,reference,height,imported_actions=actions,armature=arms[0],mesh=bound[0],surface_step=surface_step)
