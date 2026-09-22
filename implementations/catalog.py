from __future__ import annotations

from collections.abc import Callable

from ..core.pipeline_contracts import PipelineImplementation, PipelineStage
from .canonical_rig import CanonicalRigImplementation
from .native_visual_hull import NativeVisualHullImplementation
from .projected_color import ProjectedColorImplementation
from .projection_images import ProjectionImagesImplementation
from .sdf_reconstruction import SDFReconstructionImplementation
from .uv_bake import UVBakeImplementation

ImplementationFactory = Callable[[], PipelineImplementation]

# Registration order is product/UI order. Defaults remain explicit below.
BUILTIN_IMPLEMENTATION_FACTORIES: tuple[ImplementationFactory, ...] = (
    ProjectionImagesImplementation,
    NativeVisualHullImplementation,
    SDFReconstructionImplementation,
    ProjectedColorImplementation,
    UVBakeImplementation,
    CanonicalRigImplementation,
)

BUILTIN_DEFAULT_IMPLEMENTATION_IDS: dict[PipelineStage, str] = {
    PipelineStage.INPUT: "projection-images",
    PipelineStage.GEOMETRY: "native-visual-hull",
    PipelineStage.MATERIAL: "projected-color-v1.2",
    PipelineStage.RIG: "canonical-biped-v1",
}


def instantiate_builtin_implementations() -> tuple[PipelineImplementation, ...]:
    return tuple(factory() for factory in BUILTIN_IMPLEMENTATION_FACTORIES)


def validate_builtin_catalog(
    implementations: tuple[PipelineImplementation, ...],
) -> None:
    """Validate the complete catalog before mutating the runtime registry."""

    ids: set[str] = set()
    ids_by_stage = {stage: set() for stage in PipelineStage}
    for implementation in implementations:
        descriptor = implementation.descriptor
        implementation_id = descriptor.identifier
        if implementation_id in ids:
            raise RuntimeError(
                f'Duplicate built-in pipeline implementation id: "{implementation_id}".'
            )
        ids.add(implementation_id)
        ids_by_stage[descriptor.stage].add(implementation_id)

    for stage, implementation_id in BUILTIN_DEFAULT_IMPLEMENTATION_IDS.items():
        if implementation_id not in ids:
            raise RuntimeError(
                f'Built-in default implementation "{implementation_id}" for stage '
                f'"{stage.value}" does not exist in the built-in catalog.'
            )
        if implementation_id not in ids_by_stage[stage]:
            raise RuntimeError(
                f'Built-in default implementation "{implementation_id}" belongs to '
                f'the wrong pipeline stage. Expected "{stage.value}".'
            )


def builtin_default_id(stage: PipelineStage) -> str | None:
    return BUILTIN_DEFAULT_IMPLEMENTATION_IDS.get(PipelineStage(stage))
