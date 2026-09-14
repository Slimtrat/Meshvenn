from ..core.pipeline_contracts import PipelineStage
from .constants import *

PIPELINE_STAGE_PROPERTY_NAMES: dict[PipelineStage, str] = {
    PipelineStage.INPUT: "input_stage",
    PipelineStage.GEOMETRY: "geometry_stage",
    PipelineStage.MATERIAL: "material_stage",
    PipelineStage.RIG: "rig_stage",
    PipelineStage.EXPORT: "export_stage",
}

PIPELINE_STAGE_DEFAULTS: dict[PipelineStage, tuple[str, bool, bool]] = {
    PipelineStage.INPUT: (DEFAULT_INPUT_IMPLEMENTATION_ID, True, True),
    PipelineStage.GEOMETRY: (DEFAULT_GEOMETRY_IMPLEMENTATION_ID, True, True),
    PipelineStage.MATERIAL: (DEFAULT_MATERIAL_IMPLEMENTATION_ID, True, True),
    PipelineStage.RIG: (DEFAULT_RIG_IMPLEMENTATION_ID, False, False),
    PipelineStage.EXPORT: (DEFAULT_EXPORT_IMPLEMENTATION_ID, False, False),
}
