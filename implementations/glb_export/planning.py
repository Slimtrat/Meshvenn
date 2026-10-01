"""Resolve and validate the Blender objects consumed by the GLB exporter."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bpy

from ...core.geometry_contracts import GeometrySurfaceOutput, require_geometry_surface_output
from ...core.motion_contracts import MotionOutput, validate_motion_output
from ...core.pipeline_contracts import PipelineContext, PipelineStage
from ...core.rig_contracts import RigOutput, validate_rig_output


OUTPUT_PATH_METADATA_KEY = "export_output_path"
OVERWRITE_METADATA_KEY = "export_overwrite_existing"
MOTION_SOURCE_PATH_METADATA_KEY = "motion_source_path"


@dataclass(frozen=True)
class GLBExportPlan:
    path: Path
    overwrite_existing: bool
    geometry: GeometrySurfaceOutput
    mesh_object: Any
    mesh_objects: tuple[Any, ...]
    rig: RigOutput | None
    armature_object: Any | None
    motion: MotionOutput | None
    actions: tuple[Any, ...]

    @property
    def objects(self) -> tuple[Any, ...]:
        if self.armature_object is None:
            return self.mesh_objects
        return (*self.mesh_objects, self.armature_object)


def _require_scene_object(value: Any, *, object_type: str, label: str) -> Any:
    if not isinstance(value, bpy.types.Object) or value.type != object_type:
        raise TypeError(f"{label} must be a Blender {object_type} object.")
    if bpy.data.objects.get(value.name) is not value:
        raise ValueError(f"{label} is no longer present in Blender data.")
    if bpy.context.view_layer.objects.get(value.name) is not value:
        raise ValueError(f"{label} is not linked to the active Blender view layer.")
    return value


def _resolve_path(context: PipelineContext) -> tuple[Path, bool]:
    value = context.metadata.get(OUTPUT_PATH_METADATA_KEY)
    try:
        raw_path = os.fspath(value)
    except TypeError as exc:
        raise TypeError(
            f'Pipeline metadata must define "{OUTPUT_PATH_METADATA_KEY}" as a path.'
        ) from exc
    if not str(raw_path).strip():
        raise ValueError(f'Pipeline metadata must define "{OUTPUT_PATH_METADATA_KEY}".')
    # Keep the lexical destination instead of resolving it. Resolving here would
    # dereference a final symlink before the guard below and could turn an
    # overwrite into a write to the symlink target.
    path = Path(os.path.abspath(os.fspath(Path(raw_path).expanduser())))
    if path.suffix.lower() != ".glb":
        raise ValueError("GLB export output must use the .glb extension.")
    overwrite = context.metadata.get(OVERWRITE_METADATA_KEY, False)
    if not isinstance(overwrite, bool):
        raise TypeError(f'Pipeline metadata "{OVERWRITE_METADATA_KEY}" must be boolean.')
    if path.is_symlink():
        raise ValueError("GLB export output cannot be a symbolic link.")
    if path.exists() and not path.is_file():
        raise ValueError(f"GLB export output is not a regular file: {path}")
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"GLB export output already exists; enable overwrite to replace it: {path}"
        )
    if path.parent.exists() and not path.parent.is_dir():
        raise ValueError(f"GLB export parent is not a directory: {path.parent}")

    source_value = context.metadata.get(MOTION_SOURCE_PATH_METADATA_KEY)
    if source_value:
        source_path = Path(os.fspath(source_value)).expanduser().resolve(strict=False)
        resolved_output_path = path.resolve(strict=False)
        if os.path.normcase(str(source_path)) == os.path.normcase(
            str(resolved_output_path)
        ):
            raise ValueError("GLB export output cannot overwrite its Motion source file.")
    return path, overwrite


def _is_bound_to_armature(mesh: Any, armature: Any) -> bool:
    if any(
        modifier.type == "ARMATURE" and modifier.object is armature
        for modifier in mesh.modifiers
    ):
        return True
    parent = mesh.parent
    while parent is not None:
        if parent is armature:
            return True
        parent = parent.parent
    return False


def build_export_plan(context: PipelineContext) -> GLBExportPlan:
    geometry = require_geometry_surface_output(context)
    mesh = _require_scene_object(
        geometry.blender_object,
        object_type="MESH",
        label="EXPORT geometry",
    )
    mesh_objects = tuple(
        _require_scene_object(
            item,
            object_type="MESH",
            label="EXPORT geometry member",
        )
        for item in geometry.blender_objects
    )

    rig: RigOutput | None = None
    armature = None
    if context.has_output(PipelineStage.RIG):
        rig = validate_rig_output(context.require_output(PipelineStage.RIG))
        if rig.geometry is not geometry or rig.blender_object is not mesh:
            raise ValueError("EXPORT rig does not belong to the current geometry output.")
        armature = _require_scene_object(
            rig.armature_object,
            object_type="ARMATURE",
            label="EXPORT rig",
        )
        if not any(_is_bound_to_armature(item, armature) for item in mesh_objects):
            raise ValueError("EXPORT rig is not bound to any geometry mesh.")

    motion: MotionOutput | None = None
    actions: tuple[Any, ...] = ()
    if context.has_output(PipelineStage.MOTION):
        motion = validate_motion_output(context.require_output(PipelineStage.MOTION))
        if rig is None or motion.rig is not rig or motion.armature_object is not armature:
            raise ValueError("EXPORT motion does not belong to the current rig output.")
        actions = tuple(clip.action for clip in motion.clips)
        for action in actions:
            if not isinstance(action, bpy.types.Action):
                raise TypeError("EXPORT motion contains a non-Blender action.")
            if bpy.data.actions.get(action.name) is not action:
                raise ValueError(f'EXPORT motion action "{action.name}" is no longer available.')

    path, overwrite_existing = _resolve_path(context)
    return GLBExportPlan(
        path=path,
        overwrite_existing=overwrite_existing,
        geometry=geometry,
        mesh_object=mesh,
        mesh_objects=mesh_objects,
        rig=rig,
        armature_object=armature,
        motion=motion,
        actions=actions,
    )


__all__ = (
    "GLBExportPlan",
    "MOTION_SOURCE_PATH_METADATA_KEY",
    "OUTPUT_PATH_METADATA_KEY",
    "OVERWRITE_METADATA_KEY",
    "build_export_plan",
)
