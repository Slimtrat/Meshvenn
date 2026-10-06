"""Engine-neutral output contract for the EXPORT pipeline stage."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .geometry_contracts import GeometrySurfaceOutput
from .motion_contracts import MotionOutput
from .pipeline_contracts import PipelineContext, PipelineStage, validate_implementation_id
from .rig_contracts import RigOutput
from .modular_character import ModularCharacterSpec


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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


def _normalize_names(
    values: tuple[str, ...],
    *,
    name: str,
    required: bool,
) -> tuple[str, ...]:
    normalized = tuple(str(value).strip() for value in values)
    if required and not normalized:
        raise ValueError(f"ExportOutput requires at least one {name}.")
    if any(not value for value in normalized):
        raise ValueError(f"ExportOutput {name} cannot contain an empty name.")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"ExportOutput {name} must be unique.")
    return normalized


def _normalize_glb_path(value: str | os.PathLike[str]) -> Path:
    try:
        raw_value = os.fspath(value)
    except TypeError as exc:
        raise TypeError("ExportOutput path must be a string or path-like value.") from exc
    if not str(raw_value).strip():
        raise ValueError("ExportOutput requires a path.")
    path = Path(raw_value).expanduser().resolve(strict=False)
    if path.suffix.lower() != ".glb":
        raise ValueError("ExportOutput path must use the .glb extension.")
    return path


@dataclass(frozen=True)
class ExportOutput:
    geometry: GeometrySurfaceOutput
    implementation_id: str
    path: Path | str
    format: str
    size_bytes: int
    sha256: str
    object_names: tuple[str, ...]
    animation_names: tuple[str, ...] = ()
    gltf_version: str = "2.0"
    mime_type: str = "model/gltf-binary"
    rig: RigOutput | None = None
    motion: MotionOutput | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1
    modular_character: ModularCharacterSpec | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.geometry, GeometrySurfaceOutput):
            raise TypeError("ExportOutput requires a GeometrySurfaceOutput.")
        implementation_id = validate_implementation_id(self.implementation_id)
        path = _normalize_glb_path(self.path)
        export_format = str(self.format).strip().upper()
        if export_format != "GLB":
            raise ValueError('ExportOutput format must be "GLB".')
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise TypeError("ExportOutput size_bytes must be an integer.")
        if self.size_bytes <= 0:
            raise ValueError("ExportOutput size_bytes must be positive.")
        sha256 = str(self.sha256).strip()
        if not SHA256_PATTERN.fullmatch(sha256):
            raise ValueError("ExportOutput sha256 must be 64 lowercase hexadecimal characters.")
        gltf_version = str(self.gltf_version).strip()
        if gltf_version != "2.0":
            raise ValueError('ExportOutput gltf_version must be "2.0".')
        mime_type = str(self.mime_type).strip().lower()
        if mime_type != "model/gltf-binary":
            raise ValueError('ExportOutput mime_type must be "model/gltf-binary".')
        if self.rig is not None:
            if not isinstance(self.rig, RigOutput):
                raise TypeError("ExportOutput rig must be a RigOutput when provided.")
            if self.rig.geometry is not self.geometry:
                raise ValueError("ExportOutput rig must reference the exported geometry.")
        if self.motion is not None:
            if not isinstance(self.motion, MotionOutput):
                raise TypeError("ExportOutput motion must be a MotionOutput when provided.")
            if self.rig is None:
                raise ValueError("ExportOutput motion requires a rig.")
            if self.motion.rig is not self.rig:
                raise ValueError("ExportOutput motion must reference the exported rig.")
        object_names = _normalize_names(
            tuple(self.object_names), name="object_names", required=True
        )
        animation_names = _normalize_names(
            tuple(self.animation_names), name="animation_names", required=False
        )
        if self.modular_character is not None:
            if not isinstance(self.modular_character, ModularCharacterSpec):
                raise TypeError("ExportOutput modular_character must be a ModularCharacterSpec.")
            if self.rig is None or self.modular_character.rig_id != self.rig.implementation_id:
                raise ValueError("Modular export must preserve its declared native rig.")
            native_version = self.rig.implementation_id.rsplit("-v", 1)[-1]
            if not native_version.isdigit() or self.modular_character.rig_version != int(native_version):
                raise ValueError("Modular export native rig version does not match.")
            if set(self.modular_character.ownership) != {obj.name for obj in self.geometry.blender_objects}:
                raise ValueError("Modular export ownership must cover exactly the source geometry.")
            if not {region.node_name for region in self.modular_character.regions}.issubset(object_names):
                raise ValueError("Modular export object_names must include every declared region node.")
        elif self.geometry.object_name not in object_names:
            raise ValueError("ExportOutput object_names must include the geometry object.")
        if self.rig is not None:
            armature_name = str(getattr(self.rig.armature_object, "name", "")).strip()
            if not armature_name or armature_name not in object_names:
                raise ValueError("ExportOutput object_names must include the rig armature.")
        if self.motion is None and animation_names:
            raise ValueError("ExportOutput cannot contain animations without MotionOutput.")
        if self.motion is not None and len(animation_names) != len(self.motion.clips):
            raise ValueError(
                "ExportOutput animation count must match the MotionOutput clip count."
            )
        if self.schema_version != 1:
            raise ValueError("ExportOutput requires schema version 1.")
        object.__setattr__(self, "implementation_id", implementation_id)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "format", export_format)
        object.__setattr__(self, "sha256", sha256)
        object.__setattr__(self, "gltf_version", gltf_version)
        object.__setattr__(self, "mime_type", mime_type)
        object.__setattr__(
            self,
            "object_names",
            object_names,
        )
        object.__setattr__(
            self,
            "animation_names",
            animation_names,
        )
        object.__setattr__(self, "metrics", _normalize_mapping(self.metrics, name="metrics"))
        object.__setattr__(self, "metadata", _normalize_mapping(self.metadata, name="metadata"))


def validate_export_output(output: Any) -> ExportOutput:
    if not isinstance(output, ExportOutput):
        raise TypeError(f"EXPORT output must be an ExportOutput. Received {type(output).__name__}.")
    return output


def require_export_output(context: PipelineContext) -> ExportOutput:
    output = context.require_output(PipelineStage.EXPORT)
    try:
        return validate_export_output(output)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Pipeline EXPORT output is not compatible with ExportOutput. Received {type(output).__name__}."
        ) from exc


__all__ = (
    "ExportOutput",
    "validate_export_output",
    "require_export_output",
)
