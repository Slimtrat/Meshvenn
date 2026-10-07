from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from .stages import PipelineStage
if TYPE_CHECKING:
    from ..material_inputs import MaterialProjectionInput


@dataclass
class PipelineContext:
    scene: Any = None
    settings: Any = None
    source: Any = None
    outputs: dict[PipelineStage, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    material_input: MaterialProjectionInput | None = None
    # Prepared by modular authoring/source loading, never inferred by EXPORT.
    # Any keeps the generic, bpy-free pipeline independent of Blender IDs.
    prepared_modular_source: Any = None

    def set_output(self, stage: PipelineStage, value: Any) -> None:
        self.outputs[PipelineStage(stage)] = value

    def get_output(self, stage: PipelineStage, default: Any = None) -> Any:
        return self.outputs.get(PipelineStage(stage), default)

    def has_output(self, stage: PipelineStage) -> bool:
        return PipelineStage(stage) in self.outputs

    def require_output(self, stage: PipelineStage) -> Any:
        normalized_stage = PipelineStage(stage)
        if normalized_stage not in self.outputs:
            raise RuntimeError(f'Pipeline stage output "{normalized_stage.value}" is required but missing.')
        return self.outputs[normalized_stage]
