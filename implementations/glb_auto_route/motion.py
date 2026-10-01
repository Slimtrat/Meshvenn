"""MOTION stage facade for the automatic GLB character route."""

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
    PRESERVE_SOURCE_ROUTE,
    GLBRouteDecision,
)
from ..canonical_motion import CanonicalMotionRetargetImplementation
from ..glb_preservation import GLBSourceMotionImplementation
from .results import ROUTE_DECISION_METADATA_KEY, ROUTE_METADATA_KEY, routed_result


IMPLEMENTATION_ID = "glb-auto-motion-v1"


def _delegate_for_context(context: PipelineContext):
    route = str(context.metadata.get(ROUTE_METADATA_KEY, "")).strip()
    if route == PRESERVE_SOURCE_ROUTE:
        geometry = context.require_output(PipelineStage.GEOMETRY)
        if not tuple(getattr(geometry, "actions", ())):
            return route, None, "The preserved source rig contains no Motion clips."
        return route, GLBSourceMotionImplementation(), ""
    if route == CANONICALIZE_ROUTE:
        if context.metadata.get("glb_source_motion_compatible") is not True:
            return route, None, "The canonical source contains no compatible Motion."
        return route, CanonicalMotionRetargetImplementation(), ""
    return route, None, "The selected route intentionally omits Motion."


class GLBAutoMotionImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.MOTION,
        label="GLB Automatic Motion Route V1",
        description="Preserve source clips or retarget them to the routed canonical rig.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "semantic-route-selection",
            "source-action-preservation",
            "canonical-motion-retarget",
            "safe-runtime-skip",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            route, delegate, reason = _delegate_for_context(context)
            if delegate is None:
                return ImplementationAvailability.degraded(
                    reason, details={"selected_route": route}
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
        box.label(text="GLB Automatic Motion Route V1", icon="ACTION")
        box.label(text="Preserves or retargets clips according to the Rig route")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            route, delegate, reason = _delegate_for_context(context)
            if delegate is None:
                return StageExecutionResult.skipped_result(
                    stage=PipelineStage.MOTION,
                    implementation_id=IMPLEMENTATION_ID,
                    message=f"Motion omitted: {reason}",
                    metadata={"selected_route": route},
                )
            decision = GLBRouteDecision(
                **context.metadata[ROUTE_DECISION_METADATA_KEY]
            )
            return routed_result(
                delegate.execute(context),
                stage=PipelineStage.MOTION,
                implementation_id=IMPLEMENTATION_ID,
                decision=decision,
            )
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.MOTION,
                implementation_id=IMPLEMENTATION_ID,
                message=f"GLB automatic Motion routing failed: {exc}",
            )


__all__ = ("GLBAutoMotionImplementation", "IMPLEMENTATION_ID")
