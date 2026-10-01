"""RIG stage facade for the automatic GLB character route."""

from __future__ import annotations

from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.glb_route import (
    CANONICALIZE_ROUTE,
    GEOMETRY_ONLY_ROUTE,
    PRESERVE_SOURCE_ROUTE,
    GLBRouteDecision,
)
from ..canonical_rig import CanonicalRigImplementation
from ..glb_preservation import GLBSourceRigImplementation
from .results import ROUTE_METADATA_KEY, routed_result


IMPLEMENTATION_ID = "glb-auto-rig-v1"


def _selected_route(context: PipelineContext) -> str:
    route = str(context.metadata.get(ROUTE_METADATA_KEY, "")).strip()
    if not route:
        raise ValueError("Automatic GLB Geometry did not publish a route decision.")
    return route


def _delegate_for_route(route: str):
    if route == PRESERVE_SOURCE_ROUTE:
        return GLBSourceRigImplementation()
    if route == CANONICALIZE_ROUTE:
        return CanonicalRigImplementation()
    if route == GEOMETRY_ONLY_ROUTE:
        return None
    raise ValueError(f"Unsupported automatic GLB route: {route}")


class GLBAutoRigImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.RIG,
        label="GLB Automatic Rig Route V1",
        description="Expose the preserved source rig or build Canonical Biped as routed.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "semantic-route-selection",
            "canonical-biped",
            "source-rig-preservation",
            "safe-runtime-skip",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            route = _selected_route(context)
            delegate = _delegate_for_route(route)
            if delegate is None:
                return ImplementationAvailability.degraded(
                    "The selected geometry-only route intentionally omits Rig."
                )
            availability = delegate.availability(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        details = dict(availability.details)
        details.update({
            "selected_route": route,
            "delegated_implementation": delegate.descriptor.identifier,
        })
        return ImplementationAvailability(
            availability.state,
            availability.reason,
            details,
        )

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="GLB Automatic Rig Route V1", icon="ARMATURE_DATA")
        box.label(text="Uses the semantic decision made by Automatic Geometry")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            route = _selected_route(context)
            delegate = _delegate_for_route(route)
            if delegate is None:
                return StageExecutionResult.skipped_result(
                    stage=PipelineStage.RIG,
                    implementation_id=IMPLEMENTATION_ID,
                    message=(
                        "Rig omitted: no semantically safe automatic target was "
                        "identified for this GLB."
                    ),
                    metadata={"selected_route": route},
                )
            decision_data = context.metadata["glb_route_decision"]
            decision = GLBRouteDecision(**decision_data)
            return routed_result(
                delegate.execute(context),
                stage=PipelineStage.RIG,
                implementation_id=IMPLEMENTATION_ID,
                decision=decision,
            )
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.RIG,
                implementation_id=IMPLEMENTATION_ID,
                message=f"GLB automatic Rig routing failed: {exc}",
            )


__all__ = ("GLBAutoRigImplementation", "IMPLEMENTATION_ID")
