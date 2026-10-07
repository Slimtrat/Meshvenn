"""Resolve and validate the Blender objects consumed by the GLB exporter."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import bpy

from ...core.geometry_contracts import GeometrySurfaceOutput, require_geometry_surface_output
from ...core.export_paths import resolve_export_path
from ...core.glb_input_contracts import GLBFileInputOutput
from ...core.motion_contracts import MotionOutput, validate_motion_output
from ...core.pipeline_contracts import PipelineContext, PipelineStage
from ...core.rig_contracts import RigOutput, validate_rig_output
from ...core.modular_character import ModularCharacterSpec, mesh_surface_sha256
from ...core.modular_character.json_io import strict_json_loads


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
    source_paths: tuple[Path, ...] = ()
    validate_roundtrip: bool = False
    auxiliary_objects: tuple[Any, ...] = ()
    modular_spec: ModularCharacterSpec | None = None
    prepared_modular_source: Any = None

    @property
    def objects(self) -> tuple[Any, ...]:
        if self.armature_object is None:
            return (*self.mesh_objects, *self.auxiliary_objects)
        return (*self.mesh_objects, self.armature_object, *self.auxiliary_objects)


def _require_scene_object(value: Any, *, object_type: str, label: str) -> Any:
    if not isinstance(value, bpy.types.Object) or value.type != object_type:
        raise TypeError(f"{label} must be a Blender {object_type} object.")
    if bpy.data.objects.get(value.name) is not value:
        raise ValueError(f"{label} is no longer present in Blender data.")
    if bpy.context.view_layer.objects.get(value.name) is not value:
        raise ValueError(f"{label} is not linked to the active Blender view layer.")
    return value


def _source_paths(context: PipelineContext) -> tuple[Path, ...]:
    values = [context.metadata.get(key) for key in (
        "glb_input_path", MOTION_SOURCE_PATH_METADATA_KEY, "export_modular_manifest_path")]
    source = context.get_output(PipelineStage.INPUT)
    if isinstance(source, GLBFileInputOutput):
        values.append(source.path)
    geometry = context.get_output(PipelineStage.GEOMETRY)
    source = getattr(geometry, "source", None)
    if isinstance(source, GLBFileInputOutput):
        values.append(source.path)
    return tuple(dict.fromkeys(Path(value).expanduser().resolve(strict=False) for value in values if value))


def _resolve_path(context: PipelineContext) -> tuple[Path, bool]:
    overwrite = context.metadata.get(OVERWRITE_METADATA_KEY, False)
    path = resolve_export_path(
        context.metadata.get(OUTPUT_PATH_METADATA_KEY), overwrite,
        sources=_source_paths(context),
    )
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


def _modular_spec(context, meshes, rig, geometry):
    value = context.metadata.get("export_modular_spec")
    manifest_path = context.metadata.get("export_modular_manifest_path")
    enabled = context.metadata.get("export_modular_character")
    if enabled is not None and type(enabled) is not bool:
        raise TypeError("export_modular_character must be boolean.")
    if enabled is True and value is None and not manifest_path:
        raise ValueError("Modular character export is enabled but no authoring manifest is selected.")
    if enabled is False and (value is not None or manifest_path):
        raise ValueError("Modular declarations conflict with disabled modular export.")
    if value is not None and manifest_path:
        raise ValueError("Select a modular spec or manifest path, not both.")
    if manifest_path:
        path = Path(manifest_path).expanduser().resolve(strict=True)
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Modular authoring manifest exceeds 16 MiB.")
        value = strict_json_loads(path.read_text("utf-8"))
    if value is None:
        return None
    if rig is None:
        raise ValueError("Modular character export requires the original rig.")
    spec = value if isinstance(value, ModularCharacterSpec) else ModularCharacterSpec.from_dict(value)
    spec.validate_against(
        {obj.name: len(obj.data.polygons) for obj in meshes},
        tuple(rig.armature_object.data.bones.keys()), rig.implementation_id,
        mesh_surface_hashes={obj.name: mesh_surface_sha256(
            [tuple(vertex.co) for vertex in obj.data.vertices],
            [tuple(face.vertices) for face in obj.data.polygons]) for obj in meshes},
        rig_version=int(rig.implementation_id.rsplit("-v", 1)[-1]),
    )
    provenance = geometry.normalization
    if provenance is None:
        raise ValueError("Modular export requires explicit geometry normalization; load a supported authored source or repair the GEOMETRY producer.")
    declared = spec.coordinates.normalization
    if (provenance.normalized_height != declared.normalized_height
            or provenance.target_height != declared.target_height
            or not math.isclose(provenance.scale, declared.scale, rel_tol=1e-8, abs_tol=1e-12)):
        raise ValueError("Modular normalization declaration contradicts the source geometry provenance.")
    if declared.normalized_height:
        heights = [float((obj.matrix_world @ vertex.co).z) for obj in meshes for vertex in obj.data.vertices]
        if not math.isclose(max(heights) - min(heights), declared.target_height, rel_tol=1e-5, abs_tol=1e-6):
            raise ValueError("Modular target height contradicts the actual source world surface.")
    if not math.isclose(float(bpy.context.scene.unit_settings.scale_length), 1.0):
        raise ValueError("Modular V1 requires Blender world units to represent meters.")
    return spec


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
    validate_roundtrip = context.metadata.get("export_validate_roundtrip", False)
    if not isinstance(validate_roundtrip, bool):
        raise TypeError('Pipeline metadata "export_validate_roundtrip" must be boolean.')
    modular_spec = _modular_spec(context, mesh_objects, rig, geometry)
    # A modular artifact is never published without all regional fidelity gates.
    if modular_spec is not None:
        validate_roundtrip = True
    auxiliary_objects = tuple(
        _require_scene_object(obj, object_type="EMPTY", label="EXPORT hierarchy parent")
        for obj in getattr(geometry, "auxiliary_objects", ())
    )
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
        source_paths=_source_paths(context),
        validate_roundtrip=validate_roundtrip,
        auxiliary_objects=auxiliary_objects,
        modular_spec=modular_spec,
        prepared_modular_source=context.prepared_modular_source if modular_spec is not None else None,
    )


__all__ = (
    "GLBExportPlan",
    "MOTION_SOURCE_PATH_METADATA_KEY",
    "OUTPUT_PATH_METADATA_KEY",
    "OVERWRITE_METADATA_KEY",
    "build_export_plan",
)
