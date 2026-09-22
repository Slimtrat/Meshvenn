from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .stages import PipelineStage


@dataclass
class PipelineContext:
    scene: Any = None
    settings: Any = None
    source: Any = None
    outputs: dict[PipelineStage, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

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
