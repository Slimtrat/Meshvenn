from __future__ import annotations

from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from .availability import get_sdf_availability
from .config import IMPLEMENTATION_ID, IMPLEMENTATION_VERSION
from .execution import execute_sdf_reconstruction
from .ui_settings import draw_sdf_settings


class SDFReconstructionImplementation:
    """
    Experimental GEOMETRY implementation.

        INPUT views
            ↓
        BinaryMask
            ↓
        exact 2D distance transform
            ↓
        multi-view SDF fusion
            ↓
        dense SDFVolume<float>
            ↓
        continuous Surface Nets
            ↓
        normalized SDFSurfaceMesh
            ↓
        surface-envelope local coordinates
            ↓
        Blender mesh
            ↓
        GeometrySurfaceOutput

    The current backend is deliberately pure Python.

    It establishes the semantic / visual reference before
    introducing native acceleration.
    """

    _descriptor = (
        ImplementationDescriptor(
            identifier=(
                IMPLEMENTATION_ID
            ),

            stage=(
                PipelineStage.GEOMETRY
            ),

            label=(
                "SDF Reconstruction V1"
            ),

            description=(
                "Reconstruct a continuous signed-distance "
                "field from silhouette projections and "
                "extract a sub-voxel Surface Nets mesh."
            ),

            version=(
                IMPLEMENTATION_VERSION
            ),

            experimental=True,

            supports_headless=True,

            capabilities=(
                "signed-distance-field",
                "silhouette-reconstruction",
                "continuous-surface",
                "surface-nets",
                "sub-voxel",
                "multi-view",
                "symmetry-x",
                "generic-geometry",
                "projection-space",
                "python-reference",
            ),
        )
    )

    @property
    def descriptor(
        self,
    ) -> ImplementationDescriptor:
        return (
            self._descriptor
        )

    # -----------------------------------------------------
    # Availability
    # -----------------------------------------------------

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        return get_sdf_availability(context)

    def draw_settings(
        self,
        layout,
        context,
    ) -> None:
        draw_sdf_settings(layout, context)

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        return execute_sdf_reconstruction(context)
