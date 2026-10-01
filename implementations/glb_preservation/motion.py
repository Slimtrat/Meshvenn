"""MOTION stage that publishes preserved source actions without retargeting."""

from __future__ import annotations

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
from ..canonical_motion.mapping import CANONICAL_ANIMATED_ROLES
from .contracts import require_preserved_geometry


IMPLEMENTATION_ID = "glb-source-motion-v1"


def _require_source(context: PipelineContext) -> tuple[Any, RigOutput]:
    geometry = require_preserved_geometry(context.require_output(PipelineStage.GEOMETRY))
    rig = context.require_output(PipelineStage.RIG)
    if not isinstance(rig, RigOutput) or rig.implementation_id != "glb-source-rig-v1":
        raise TypeError("Source Motion requires GLB Source Rig Preservation V1.")
    if rig.geometry is not geometry or rig.armature_object is not geometry.armature_object:
        raise ValueError("Preserved source Motion does not belong to the current rig.")
    if not geometry.actions:
        raise ValueError("Preserved GLB source contains no armature actions.")
    for action in geometry.actions:
        if not isinstance(action, bpy.types.Action):
            raise TypeError("Preserved source action is not a Blender action.")
        if bpy.data.actions.get(action.name) is not action:
            raise ValueError(f'Preserved action "{action.name}" is no longer available.')
    return geometry, rig


def _keyframe_point_count(action: Any) -> int:
    try:
        return sum(len(curve.keyframe_points) for curve in action.fcurves)
    except (AttributeError, RuntimeError, TypeError):
        return 0


class GLBSourceMotionImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.MOTION,
        label="GLB Source Motion Preservation V1",
        description="Publish imported GLB actions without retargeting or root-motion loss.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "source-action-preservation",
            "multi-clip",
            "preserved-root-motion",
            "humanoid",
            "quadruped",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            geometry, rig = _require_source(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        return ImplementationAvailability.ready_state(details={
            "profile": geometry.source_profile_id,
            "rig_implementation": rig.implementation_id,
            "action_count": len(geometry.actions),
            "root_motion_mode": "PRESERVE",
        })

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="GLB Source Motion Preservation V1", icon="ACTION")
        box.label(text="Keeps source clips and root motion unchanged")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            geometry, rig = _require_source(context)
            roles = tuple(
                role for role in CANONICAL_ANIMATED_ROLES
                if role in geometry.semantic_bones
            )
            fps = (
                context.scene.render.fps / context.scene.render.fps_base
                if context.scene is not None
                else bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
            )
            clips = tuple(
                MotionClipOutput(
                    name=action.name,
                    action=action,
                    frame_start=float(action.frame_range[0]),
                    frame_end=float(action.frame_range[1]),
                    fps=fps,
                    animated_roles=roles,
                    metadata={"preserved": True},
                )
                for action in geometry.actions
            )
            keyframe_points = sum(
                _keyframe_point_count(action) for action in geometry.actions
            )
            metrics = {
                "source_profile": geometry.source_profile_id,
                "source_profile_certification": (
                    geometry.source_profile_certification
                ),
                "source_rig_archetype": geometry.source_rig_archetype,
                "clip_count": len(clips),
                "mapped_role_count": len(roles),
                "pose_samples": max(keyframe_points, len(clips)),
                "preserved_keyframe_points": keyframe_points,
                "root_motion_mode": "PRESERVE",
            }
            source_map = {
                role: geometry.semantic_bones[role] for role in roles
            }
            output = MotionOutput(
                rig=rig,
                armature_object=rig.armature_object,
                implementation_id=IMPLEMENTATION_ID,
                clips=clips,
                source_bone_map=source_map,
                root_motion_mode="PRESERVE",
                metrics=metrics,
                metadata={"source_actions_preserved": True},
            )
            context.metadata.update({
                "motion_source_profile": geometry.source_profile_id,
                "motion_source_profile_certification": (
                    geometry.source_profile_certification
                ),
                "motion_source_rig_archetype": geometry.source_rig_archetype,
                "motion_clip_names": tuple(clip.name for clip in clips),
                "motion_root_mode": "PRESERVE",
            })
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.MOTION,
                implementation_id=IMPLEMENTATION_ID,
                message=f"Cannot publish preserved GLB Motion: {exc}",
            )
        return StageExecutionResult.succeeded(
            stage=PipelineStage.MOTION,
            implementation_id=IMPLEMENTATION_ID,
            payload=output,
            message=f"Preserved {len(clips)} source action(s) with root motion.",
            metrics=metrics,
            metadata={
                "source_profile": geometry.source_profile_id,
                "actions": tuple(action.name for action in geometry.actions),
            },
        )


__all__ = ("GLBSourceMotionImplementation", "IMPLEMENTATION_ID")
