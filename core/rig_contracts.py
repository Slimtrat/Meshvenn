"""Engine-neutral output contract for the RIG pipeline stage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .geometry_contracts import GeometrySurfaceOutput
from .pipeline_contracts import PipelineContext, PipelineStage, validate_implementation_id


@dataclass(frozen=True)
class RigOutput:
    geometry: GeometrySurfaceOutput
    blender_object: Any
    armature_object: Any
    implementation_id: str
    semantic_bones: Mapping[str, str]
    binding_method: str
    schema_version: int = 1
    up_axis: str = "Z"
    forward_axis: str = "-Y"
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.geometry, GeometrySurfaceOutput):
            raise TypeError("RigOutput requires a GeometrySurfaceOutput.")
        if self.blender_object is not self.geometry.blender_object:
            raise ValueError("RigOutput mesh must be the geometry surface object.")
        if self.armature_object is None:
            raise ValueError("RigOutput requires an armature object.")
        object.__setattr__(self, "implementation_id", validate_implementation_id(self.implementation_id))
        bones = dict(self.semantic_bones)
        if not bones or any(not role or not name for role, name in bones.items()):
            raise ValueError("RigOutput requires nonempty semantic bone mappings.")
        object.__setattr__(self, "semantic_bones", bones)
        if not self.binding_method:
            raise ValueError("RigOutput requires a binding method.")
        if self.schema_version != 1 or self.up_axis != "Z" or self.forward_axis != "-Y":
            raise ValueError("Canonical rig output requires schema 1, Z up, and -Y forward.")
        object.__setattr__(self, "metrics", dict(self.metrics))


def validate_rig_output(output: Any) -> RigOutput:
    if not isinstance(output, RigOutput):
        raise TypeError(f"RIG output must be a RigOutput. Received {type(output).__name__}.")
    return output


def require_rig_output(context: PipelineContext) -> RigOutput:
    output = context.require_output(PipelineStage.RIG)
    try:
        return validate_rig_output(output)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"Pipeline RIG output is not compatible with RigOutput. Received {type(output).__name__}."
        ) from exc
