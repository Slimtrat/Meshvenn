"""Built-in external-GLB motion retarget implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpy

from ...core.motion_contracts import MotionClipOutput, MotionOutput
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.rig_contracts import RigOutput
from ...core.rig_compatibility import require_target_compatibility
from .mapping import SOURCE_PROFILES, resolve_bone_map, validate_target_rig
from .retarget import (
    ROOT_MOTION_MODE,
    bake_retargeted_action,
    restore_target_animation,
    snapshot_target_animation,
)
from .source import cleanup_imported_data, import_external_motion, snapshot_blender_data


IMPLEMENTATION_ID = "canonical-motion-retarget-v1"
SOURCE_PATH_METADATA_KEY = "motion_source_path"


@dataclass(frozen=True)
class _BlenderState:
    frame_current: int
    frame_start: int
    frame_end: int
    active_object: Any
    selected_objects: tuple[Any, ...]
    active_mode: str


def _capture_blender_state(scene: Any) -> _BlenderState:
    active = bpy.context.view_layer.objects.active
    return _BlenderState(
        frame_current=scene.frame_current,
        frame_start=scene.frame_start,
        frame_end=scene.frame_end,
        active_object=active,
        selected_objects=tuple(bpy.context.selected_objects),
        active_mode=active.mode if active is not None else "OBJECT",
    )


def _restore_blender_state(scene: Any, state: _BlenderState) -> None:
    scene.frame_start = state.frame_start
    scene.frame_end = state.frame_end
    scene.frame_set(state.frame_current)
    for obj in tuple(bpy.context.selected_objects):
        obj.select_set(False)
    for obj in state.selected_objects:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    if state.active_object is not None and state.active_object.name in bpy.data.objects:
        bpy.context.view_layer.objects.active = state.active_object
        if state.active_mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode=state.active_mode)
            except RuntimeError:
                pass
    else:
        bpy.context.view_layer.objects.active = None
    bpy.context.view_layer.update()


def _require_target(context: PipelineContext) -> tuple[RigOutput, Any, Path]:
    rig = context.require_output(PipelineStage.RIG)
    if not isinstance(rig, RigOutput):
        raise TypeError("Canonical motion requires a RigOutput from the RIG stage")
    armature = rig.armature_object
    if not isinstance(armature, bpy.types.Object) or armature.type != "ARMATURE":
        raise TypeError("Canonical motion requires a Blender armature target")
    source_value = context.metadata.get(SOURCE_PATH_METADATA_KEY)
    if not source_value:
        raise ValueError(f'Pipeline metadata must define "{SOURCE_PATH_METADATA_KEY}"')
    source_path = Path(source_value).expanduser().resolve()
    if source_path.suffix.lower() != ".glb":
        raise ValueError("Canonical motion source must be an external .glb file")
    if not source_path.is_file():
        raise FileNotFoundError(f"Motion source GLB does not exist: {source_path}")
    if context.metadata.get("glb_target_rig_compatible") is False:
        archetype = context.metadata.get("glb_source_rig_archetype", "unknown")
        raise ValueError(
            f'GLB source rig archetype "{archetype}" is not compatible with '
            f'target rig "{rig.implementation_id}".'
        )
    validate_target_rig(
        rig.semantic_bones,
        armature.data.bones.keys(),
    )
    return rig, armature, source_path


class CanonicalMotionRetargetImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.MOTION,
        label="Canonical Motion Retarget V1",
        description="Detect and bake supported GLB skeleton animation onto a Canonical Biped rig.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "external-glb-motion",
            "multi-skeleton-profiles",
            "namespace-tolerant-bone-mapping",
            "rest-space-retarget",
            "baked-quaternion-action",
            "in-place-root",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            rig, armature, source_path = _require_target(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        return ImplementationAvailability.ready_state(details={
            "rig_implementation": rig.implementation_id,
            "target_armature": armature.name,
            "source_path": str(source_path),
            "root_motion_mode": ROOT_MOTION_MODE,
        })

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="Canonical Motion Retarget V1", icon="ACTION")
        settings = getattr(getattr(context, "scene", None), "bpt_settings", None)
        if settings is None:
            warning = box.row()
            warning.alert = True
            warning.label(text="Meshvenn settings unavailable", icon="ERROR")
            return
        box.prop(settings, "motion_source_path", text="Source GLB")
        if not settings.motion_source_path.strip():
            warning = box.row()
            warning.alert = True
            warning.label(text="Choose an animated GLB source", icon="INFO")
        box.label(text=f"Profiles: {len(SOURCE_PROFILES)} deterministic adapters")
        box.label(text="17 semantic roles; root remains in place")


    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            rig, target_armature, source_path = _require_target(context)
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.MOTION,
                implementation_id=IMPLEMENTATION_ID,
                message=f"Cannot prepare canonical motion retarget: {exc}",
            )

        scene = context.scene if context.scene is not None else bpy.context.scene
        blender_state = _capture_blender_state(scene)
        data_snapshot = snapshot_blender_data()
        target_snapshot = None
        generated_actions: list[Any] = []
        succeeded = False
        try:
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            imported = import_external_motion(source_path, data_snapshot)
            require_target_compatibility(
                imported.profile.identifier,
                imported.profile.rig_archetype,
                imported.profile.compatible_target_rigs,
                rig.implementation_id,
            )
            bone_map = resolve_bone_map(
                (bone.name for bone in imported.armature.data.bones),
                rig.semantic_bones,
                target_armature.data.bones.keys(),
            )
            root_bone = rig.semantic_bones["root"]
            target_snapshot = snapshot_target_animation(
                target_armature,
                (root_bone, *(entry.target_bone for entry in bone_map.entries)),
            )
            fps = scene.render.fps / scene.render.fps_base
            baked = []
            for source_action in imported.actions:
                result = bake_retargeted_action(
                    imported.armature,
                    target_armature,
                    source_action,
                    bone_map,
                    root_bone=root_bone,
                    fps=fps,
                    action_name=f"Meshvenn_{source_action.name}",
                )
                generated_actions.append(result.action)
                baked.append(result)
            if not baked:
                raise RuntimeError("No source animation was baked")

            clips = tuple(
                MotionClipOutput(
                    name=item.name,
                    action=item.action,
                    frame_start=item.frame_start,
                    frame_end=item.frame_end,
                    fps=item.fps,
                    animated_roles=item.animated_roles,
                )
                for item in baked
            )
            total_samples = sum(item.pose_samples for item in baked)
            metrics = {
                "source_profile": bone_map.profile_id,
                "source_profile_certification": imported.profile.certification,
                "source_rig_archetype": imported.profile.rig_archetype,
                "target_rig_compatible": True,
                "clip_count": len(clips),
                "mapped_role_count": len(bone_map.entries),
                "baked_pose_samples": total_samples,
                "pose_samples": total_samples,
                "root_motion_mode": ROOT_MOTION_MODE,
            }
            output = MotionOutput(
                rig=rig,
                armature_object=target_armature,
                implementation_id=IMPLEMENTATION_ID,
                clips=clips,
                source_bone_map=bone_map.source_bone_map,
                root_motion_mode=ROOT_MOTION_MODE,
                metrics=metrics,
            )
            target_armature.animation_data_create().action = generated_actions[0]
            context.metadata["motion_source_profile"] = bone_map.profile_id
            context.metadata["motion_source_profile_certification"] = (
                imported.profile.certification
            )
            context.metadata["motion_source_rig_archetype"] = (
                imported.profile.rig_archetype
            )
            context.metadata["motion_clip_names"] = tuple(clip.name for clip in clips)
            context.metadata["motion_root_mode"] = ROOT_MOTION_MODE
            succeeded = True
            return StageExecutionResult.succeeded(
                stage=PipelineStage.MOTION,
                implementation_id=IMPLEMENTATION_ID,
                payload=output,
                message=(
                    f"Retargeted {len(clips)} clip(s) across {len(bone_map.entries)} "
                    "canonical roles with in-place root motion."
                ),
                metrics=metrics,
                metadata={
                    "source_path": str(source_path),
                    "source_profile": bone_map.profile_id,
                    "source_profile_certification": imported.profile.certification,
                    "target_armature": target_armature.name,
                    "actions": tuple(action.name for action in generated_actions),
                },
            )
        except Exception as exc:
            if target_snapshot is not None:
                restore_target_animation(target_armature, target_snapshot)
            return StageExecutionResult.failed_result(
                stage=PipelineStage.MOTION,
                implementation_id=IMPLEMENTATION_ID,
                message=f"Canonical motion retarget failed: {exc}",
                metadata={"source_path": str(source_path)},
            )
        finally:
            cleanup_imported_data(
                data_snapshot,
                preserve_actions=tuple(generated_actions) if succeeded else (),
            )
            _restore_blender_state(scene, blender_state)


__all__ = (
    "IMPLEMENTATION_ID",
    "SOURCE_PATH_METADATA_KEY",
    "CanonicalMotionRetargetImplementation",
)
