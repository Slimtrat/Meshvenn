from __future__ import annotations

from collections.abc import Iterable

from ..pipeline_contracts import PIPELINE_STAGE_ORDER, PipelineImplementation, PipelinePlan, PipelineStage, PipelineStageSelection
from .registry import PipelineRegistry


def build_default_plan(registry: PipelineRegistry, *, include_optional: bool = True) -> PipelinePlan:
    optional = {PipelineStage.MATERIAL, PipelineStage.RIG, PipelineStage.EXPORT}
    selections = []
    for stage in PIPELINE_STAGE_ORDER:
        if not include_optional and stage in optional:
            continue
        identifier = registry.default_id(stage)
        if identifier is not None:
            selections.append(PipelineStageSelection(stage, identifier, True))
    return PipelinePlan(tuple(selections))


def register_many(registry: PipelineRegistry, implementations: Iterable[PipelineImplementation], *, replace: bool = False) -> None:
    for implementation in implementations:
        registry.register(implementation, replace=replace)
