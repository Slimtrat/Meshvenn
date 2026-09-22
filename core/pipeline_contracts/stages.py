from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PipelineStage(str, Enum):
    INPUT = "input"
    GEOMETRY = "geometry"
    MATERIAL = "material"
    RIG = "rig"
    EXPORT = "export"


@dataclass(frozen=True)
class PipelineStageSpec:
    stage: PipelineStage
    label: str
    description: str
    required_stages: tuple[PipelineStage, ...] = ()
    optional: bool = False


PIPELINE_STAGE_SPECS: tuple[PipelineStageSpec, ...] = (
    PipelineStageSpec(PipelineStage.INPUT, "Input", "Images, projection views and source data."),
    PipelineStageSpec(PipelineStage.GEOMETRY, "Geometry", "Reconstruct the 3D surface from the source data.", (PipelineStage.INPUT,)),
    PipelineStageSpec(PipelineStage.MATERIAL, "Material", "Generate appearance information for the mesh.", (PipelineStage.GEOMETRY,), True),
    PipelineStageSpec(PipelineStage.RIG, "Rig", "Generate or attach a skeleton and skinning data.", (PipelineStage.GEOMETRY,), True),
    PipelineStageSpec(PipelineStage.EXPORT, "Export", "Prepare and export the generated asset.", (PipelineStage.GEOMETRY,), True),
)
PIPELINE_STAGE_ORDER = tuple(spec.stage for spec in PIPELINE_STAGE_SPECS)
PIPELINE_STAGE_SPEC_BY_STAGE = {spec.stage: spec for spec in PIPELINE_STAGE_SPECS}


def stage_spec(stage: PipelineStage) -> PipelineStageSpec:
    try:
        return PIPELINE_STAGE_SPEC_BY_STAGE[PipelineStage(stage)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Unknown pipeline stage: {stage}") from exc
