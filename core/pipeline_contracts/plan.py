from __future__ import annotations

from dataclasses import dataclass

from .identifiers import validate_implementation_id
from .stages import PIPELINE_STAGE_ORDER, PipelineStage


@dataclass(frozen=True)
class PipelineStageSelection:
    stage: PipelineStage
    implementation_id: str
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", PipelineStage(self.stage))
        object.__setattr__(self, "implementation_id", validate_implementation_id(self.implementation_id))


@dataclass(frozen=True)
class PipelinePlan:
    selections: tuple[PipelineStageSelection, ...]

    def __post_init__(self) -> None:
        selection_by_stage: dict[PipelineStage, PipelineStageSelection] = {}
        for selection in self.selections:
            if selection.stage in selection_by_stage:
                raise ValueError(f'Pipeline plan contains duplicate stage "{selection.stage.value}".')
            selection_by_stage[selection.stage] = selection
        object.__setattr__(self, "selections", tuple(selection_by_stage[stage] for stage in PIPELINE_STAGE_ORDER if stage in selection_by_stage))

    def selection_for(self, stage: PipelineStage) -> PipelineStageSelection | None:
        normalized_stage = PipelineStage(stage)
        return next((selection for selection in self.selections if selection.stage == normalized_stage), None)

    def enabled_selection_for(self, stage: PipelineStage) -> PipelineStageSelection | None:
        selection = self.selection_for(stage)
        return selection if selection is not None and selection.enabled else None

    @property
    def enabled_selections(self) -> tuple[PipelineStageSelection, ...]:
        return tuple(selection for selection in self.selections if selection.enabled)
