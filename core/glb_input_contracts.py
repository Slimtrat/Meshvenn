"""Engine-neutral contract for a validated GLB pipeline input."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .pipeline_contracts import PipelineContext, PipelineStage, validate_implementation_id


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _names(values: tuple[str, ...], *, label: str) -> tuple[str, ...]:
    normalized = tuple(str(value).strip() for value in values)
    if any(not value for value in normalized):
        raise ValueError(f"{label} cannot contain an empty name.")
    return normalized


@dataclass(frozen=True)
class GLBFileInputOutput:
    path: Path | str
    implementation_id: str
    size_bytes: int
    sha256: str
    node_names: tuple[str, ...]
    animation_names: tuple[str, ...]
    scene_count: int
    mesh_count: int
    skin_count: int
    material_count: int
    gltf_version: str = "2.0"
    mime_type: str = "model/gltf-binary"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self) -> None:
        try:
            raw_path = os.fspath(self.path)
        except TypeError as exc:
            raise TypeError("GLB input path must be string or path-like.") from exc
        path = Path(raw_path).expanduser().resolve(strict=False)
        if path.suffix.lower() != ".glb":
            raise ValueError("GLB input path must use the .glb extension.")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise TypeError("GLB input size must be an integer.")
        if self.size_bytes <= 0:
            raise ValueError("GLB input size must be positive.")
        sha256 = str(self.sha256).strip()
        if not SHA256_PATTERN.fullmatch(sha256):
            raise ValueError("GLB input SHA-256 must be lowercase hexadecimal.")
        if str(self.gltf_version).strip() != "2.0":
            raise ValueError("GLB input must declare glTF 2.0.")
        if str(self.mime_type).strip().lower() != "model/gltf-binary":
            raise ValueError("GLB input MIME type must be model/gltf-binary.")
        for name, value, minimum in (
            ("scene_count", self.scene_count, 1),
            ("mesh_count", self.mesh_count, 1),
            ("skin_count", self.skin_count, 0),
            ("material_count", self.material_count, 0),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"GLB input {name} must be an integer.")
            if value < minimum:
                raise ValueError(f"GLB input {name} must be at least {minimum}.")
        if self.schema_version != 1:
            raise ValueError("GLB input requires schema version 1.")
        metadata = dict(self.metadata)
        if any(not str(key).strip() for key in metadata):
            raise ValueError("GLB input metadata keys cannot be empty.")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "implementation_id", validate_implementation_id(self.implementation_id))
        object.__setattr__(self, "sha256", sha256)
        object.__setattr__(self, "node_names", _names(tuple(self.node_names), label="node_names"))
        object.__setattr__(self, "animation_names", _names(tuple(self.animation_names), label="animation_names"))
        object.__setattr__(self, "gltf_version", "2.0")
        object.__setattr__(self, "mime_type", "model/gltf-binary")
        object.__setattr__(self, "metadata", metadata)

    @property
    def animated(self) -> bool:
        return bool(self.animation_names)

    @property
    def skinned(self) -> bool:
        return self.skin_count > 0


def validate_glb_file_input(output: Any) -> GLBFileInputOutput:
    if not isinstance(output, GLBFileInputOutput):
        raise TypeError(
            "GLB-first INPUT output must be a GLBFileInputOutput. "
            f"Received {type(output).__name__}."
        )
    return output


def require_glb_file_input(context: PipelineContext) -> GLBFileInputOutput:
    return validate_glb_file_input(context.require_output(PipelineStage.INPUT))


__all__ = (
    "GLBFileInputOutput",
    "require_glb_file_input",
    "validate_glb_file_input",
)
