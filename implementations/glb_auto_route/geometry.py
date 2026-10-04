"""GEOMETRY stage that resolves a GLB route before mutating the scene."""

from __future__ import annotations

import bpy

from ...core.glb_input_contracts import require_glb_file_input
from ...core.glb_route import (
    CANONICALIZE_ROUTE,
    GEOMETRY_ONLY_ROUTE,
    PRESERVE_SOURCE_ROUTE,
    GLBRouteDecision,
    decide_glb_character_route,
)
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..canonical_motion.mapping import resolve_source_profile
from ..glb_geometry import GLBNormalizedGeometryImplementation
from ..glb_preservation import GLBPreservedGeometryImplementation
from .results import publish_route, routed_result


IMPLEMENTATION_ID = "glb-auto-geometry-v1"


def resolve_glb_route(context: PipelineContext) -> GLBRouteDecision:
    source = require_glb_file_input(context)
    try:
        # Node labels outside the skin are not skeleton evidence.
        resolved = resolve_source_profile(source.metadata.get("skin_joint_names", ()))
    except ValueError:
        return decide_glb_character_route(
            source_skin_count=source.skin_count,
            source_profile=None,
            source_animation_count=len(source.animation_names),
            source_morph_target_count=source.metadata.get("morph_target_count", 0),
        )
    profile = resolved.profile
    return decide_glb_character_route(
        source_skin_count=source.skin_count,
        source_profile=profile.identifier,
        source_archetype=profile.rig_archetype,
        source_certification=profile.certification,
        compatible_targets=profile.compatible_target_rigs,
        source_animation_count=len(source.animation_names),
        source_morph_target_count=source.metadata.get("morph_target_count", 0),
    )


class GLBAutoGeometryImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.GEOMETRY,
        label="GLB Automatic Character Route V1",
        description=(
            "Preserve E2E-tested source rigs; report data losses for geometry-only "
            "fallbacks. Canonicalization remains an explicit conversion."
        ),
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "glb-first",
            "semantic-route-selection",
            "canonical-humanoid",
            "source-rig-preservation",
            "safe-geometry-fallback",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            source = require_glb_file_input(context)
            decision = resolve_glb_route(context)
            if bpy.context.scene is None:
                raise RuntimeError("No active Blender scene.")
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        details = {
            "path": str(source.path),
            "selected_route": decision.route,
            "route_reason": decision.reason,
            "source_profile": decision.source_profile,
            "source_archetype": decision.source_archetype,
            "losses": decision.losses,
        }
        if decision.losses:
            return ImplementationAvailability.degraded(
                "Geometry-only export loses " + ", ".join(decision.losses), details=details,
            )
        return ImplementationAvailability.ready_state(details=details)

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="GLB Automatic Character Route V1", icon="SORTBYEXT")
        settings = getattr(getattr(context, "scene", None), "bpt_settings", None)
        if settings is None:
            box.label(text="Meshvenn settings unavailable", icon="ERROR")
            return
        box.prop(settings, "glb_normalized_extent", text="Normalized Size")
        box.label(text="Supported rigs → Preserve; conversion is opt-in")
        box.label(text="Unknown rigs → Geometry only (rig/clip loss)", icon="ERROR")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            decision = resolve_glb_route(context)
            if decision.route == PRESERVE_SOURCE_ROUTE:
                delegate = GLBPreservedGeometryImplementation()
            else:
                delegate = GLBNormalizedGeometryImplementation()
            result = delegate.execute(context)
            if result.success and decision.route == CANONICALIZE_ROUTE:
                if context.metadata.get("glb_target_rig_compatible") is not True:
                    decision = GLBRouteDecision(
                        GEOMETRY_ONLY_ROUTE,
                        "Imported rig evidence did not validate the canonical target.",
                        decision.source_profile,
                        decision.source_archetype,
                        decision.source_certification,
                    )
            publish_route(context, decision)
            return routed_result(
                result,
                stage=PipelineStage.GEOMETRY,
                implementation_id=IMPLEMENTATION_ID,
                decision=decision,
            )
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.GEOMETRY,
                implementation_id=IMPLEMENTATION_ID,
                message=f"GLB automatic route resolution failed: {exc}",
            )


__all__ = (
    "GLBAutoGeometryImplementation",
    "IMPLEMENTATION_ID",
    "resolve_glb_route",
)
