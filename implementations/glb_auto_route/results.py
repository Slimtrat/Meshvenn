"""Result and context helpers shared by automatic GLB route stages."""

from __future__ import annotations

from ...core.pipeline_contracts import (
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.glb_route import GLBRouteDecision


ROUTE_METADATA_KEY = "glb_character_route"
ROUTE_DECISION_METADATA_KEY = "glb_route_decision"


def publish_route(context: PipelineContext, decision: GLBRouteDecision) -> None:
    context.metadata[ROUTE_METADATA_KEY] = decision.route
    context.metadata[ROUTE_DECISION_METADATA_KEY] = decision.as_dict()
    context.metadata["glb_route_reason"] = decision.reason
    context.metadata["glb_route_losses"] = decision.losses
    context.metadata["glb_route_degraded"] = bool(decision.losses)


def routed_result(
    result: StageExecutionResult,
    *,
    stage: PipelineStage,
    implementation_id: str,
    decision: GLBRouteDecision,
) -> StageExecutionResult:
    metrics = dict(result.metrics)
    metrics["selected_route"] = decision.route
    metadata = dict(result.metadata)
    metadata.update({
        "selected_route": decision.route,
        "route_reason": decision.reason,
        "delegated_implementation": result.implementation_id,
        "route_losses": decision.losses,
        "route_degraded": bool(decision.losses),
    })
    return StageExecutionResult(
        stage=stage,
        implementation_id=implementation_id,
        state=result.state,
        payload=result.payload,
        message=(f"Auto route {decision.route}: {result.message}"
                 + (" WARNING: loses " + ", ".join(decision.losses) if decision.losses else "")),
        metrics=metrics,
        metadata=metadata,
    )


__all__ = (
    "ROUTE_DECISION_METADATA_KEY",
    "ROUTE_METADATA_KEY",
    "publish_route",
    "routed_result",
)
