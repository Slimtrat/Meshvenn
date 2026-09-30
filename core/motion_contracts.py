"""Engine-neutral output contract for the MOTION pipeline stage."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from .pipeline_contracts import PipelineContext, PipelineStage, validate_implementation_id
from .rig_contracts import RigOutput


def _normalize_mapping(value: Mapping[str, Any] | None, *, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping.")
    result: dict[str, Any] = {}
    for key, item in value.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            raise ValueError(f"{name} cannot contain an empty key.")
        result[normalized_key] = item
    return result


def _normalize_roles(roles: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for role in roles:
        value = str(role).strip()
        if not value:
            raise ValueError("Motion clip roles cannot be empty.")
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    if not normalized:
        raise ValueError("MotionClipOutput requires at least one animated role.")
    return tuple(normalized)


@dataclass(frozen=True)
class MotionClipOutput:
    name: str
    action: Any
    frame_start: float
    frame_end: float
    fps: float
    animated_roles: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise ValueError("MotionClipOutput requires a name.")
        if self.action is None:
            raise ValueError("MotionClipOutput requires an action.")
        frame_start = float(self.frame_start)
        frame_end = float(self.frame_end)
        fps = float(self.fps)
        if not all(math.isfinite(value) for value in (frame_start, frame_end, fps)):
            raise ValueError("Motion clip timing must be finite.")
        if frame_end <= frame_start:
            raise ValueError("Motion clip frame_end must follow frame_start.")
        if fps <= 0.0:
            raise ValueError("Motion clip fps must be positive.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "frame_start", frame_start)
        object.__setattr__(self, "frame_end", frame_end)
        object.__setattr__(self, "fps", fps)
        object.__setattr__(self, "animated_roles", _normalize_roles(tuple(self.animated_roles)))
        object.__setattr__(self, "metadata", _normalize_mapping(self.metadata, name="metadata"))

    @property
    def duration_seconds(self) -> float:
        return (self.frame_end - self.frame_start) / self.fps


@dataclass(frozen=True)
class MotionOutput:
    rig: RigOutput
    armature_object: Any
    implementation_id: str
    clips: tuple[MotionClipOutput, ...]
    source_bone_map: Mapping[str, str]
    root_motion_mode: str = "IN_PLACE"
    metrics: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.rig, RigOutput):
            raise TypeError("MotionOutput requires a RigOutput.")
        if self.armature_object is not self.rig.armature_object:
            raise ValueError("MotionOutput armature must be the RIG output armature.")
        implementation_id = validate_implementation_id(self.implementation_id)
        clips = tuple(self.clips)
        if not clips or any(not isinstance(clip, MotionClipOutput) for clip in clips):
            raise ValueError("MotionOutput requires one or more MotionClipOutput clips.")
        names = [clip.name for clip in clips]
        if len(names) != len(set(names)):
            raise ValueError("MotionOutput clip names must be unique.")
        source_bone_map = _normalize_mapping(self.source_bone_map, name="source_bone_map")
        if not source_bone_map or any(not str(value).strip() for value in source_bone_map.values()):
            raise ValueError("MotionOutput requires a nonempty source bone map.")
        source_bone_map = {role: str(name).strip() for role, name in source_bone_map.items()}
        mapped_roles = set(source_bone_map)
        unknown_roles = sorted(mapped_roles - set(self.rig.semantic_bones))
        if unknown_roles:
            raise ValueError(
                "Motion source map contains roles absent from the target rig: "
                + ", ".join(unknown_roles)
            )
        missing_roles = sorted({role for clip in clips for role in clip.animated_roles} - mapped_roles)
        if missing_roles:
            raise ValueError(
                "Animated roles are missing from source_bone_map: " + ", ".join(missing_roles)
            )
        root_motion_mode = str(self.root_motion_mode).strip().upper()
        if root_motion_mode not in {"IN_PLACE", "PRESERVE"}:
            raise ValueError('root_motion_mode must be "IN_PLACE" or "PRESERVE".')
        if self.schema_version != 1:
            raise ValueError("MotionOutput requires schema version 1.")
        object.__setattr__(self, "implementation_id", implementation_id)
        object.__setattr__(self, "clips", clips)
        object.__setattr__(self, "source_bone_map", source_bone_map)
        object.__setattr__(self, "root_motion_mode", root_motion_mode)
        object.__setattr__(self, "metrics", _normalize_mapping(self.metrics, name="metrics"))
        object.__setattr__(self, "metadata", _normalize_mapping(self.metadata, name="metadata"))


def validate_motion_clip_output(output: Any) -> MotionClipOutput:
    if not isinstance(output, MotionClipOutput):
        raise TypeError(
            f"MOTION clip must be a MotionClipOutput. Received {type(output).__name__}."
        )
    return output


def validate_motion_output(output: Any) -> MotionOutput:
    if not isinstance(output, MotionOutput):
        raise TypeError(f"MOTION output must be a MotionOutput. Received {type(output).__name__}.")
    return output


def require_motion_output(context: PipelineContext) -> MotionOutput:
    output = context.require_output(PipelineStage.MOTION)
    try:
        return validate_motion_output(output)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Pipeline MOTION output is not compatible with MotionOutput. Received {type(output).__name__}."
        ) from exc


__all__ = (
    "MotionClipOutput",
    "MotionOutput",
    "validate_motion_clip_output",
    "validate_motion_output",
    "require_motion_output",
)
