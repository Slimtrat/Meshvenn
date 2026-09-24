"""Canonical Biped V2 pipeline implementation."""

from __future__ import annotations

import json

import bpy

from ...core.canonical_rig import bounds_from_vertices
from ...core.canonical_rig_v2 import fit_canonical_biped_v2
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.rig_contracts import RigOutput
from ...core.rig_quality import assess_biped_geometry
from ..canonical_rig.binding import (
    _remove_new_binding,
    bind_mesh_deterministic,
    create_armature,
)
from ..canonical_rig.implementation import _require_mesh

IMPLEMENTATION_ID = "canonical-biped-v2"


def _prepare(context: PipelineContext):
    geometry, mesh = _require_mesh(context)
    vertices = tuple(tuple(vertex.co) for vertex in mesh.data.vertices)
    bounds = bounds_from_vertices(vertices)
    quality = assess_biped_geometry(vertices, bounds)
    if "low_height_to_width" in quality.warnings:
        raise ValueError("Canonical Biped V2 requires an upright biped silhouette.")
    bones, fit = fit_canonical_biped_v2(vertices)
    if fit.confidence < 0.25:
        raise ValueError("Canonical Biped V2 could not observe both arm envelopes.")
    existing = {group.name for group in mesh.vertex_groups}
    conflicts = existing.intersection(spec.name for spec in bones)
    if conflicts:
        raise ValueError(
            "Existing vertex groups conflict with Canonical Biped V2 bones: "
            + ", ".join(sorted(conflicts))
        )
    return geometry, mesh, bounds, bones, quality, fit


class CanonicalRigV2Implementation:
    """Fit pose-aware canonical anchors and deterministic regional skinning."""

    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.RIG,
        label="Canonical Biped V2",
        description="Fit an envelope-guided biped rig with deterministic skinning.",
        version="2",
        experimental=True,
        supports_headless=True,
        capabilities=(
            "canonical-biped", "semantic-bones", "envelope-guided-fit",
            "deterministic-skinning", "glb-ready",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            geometry, mesh, bounds, _, quality, fit = _prepare(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        return ImplementationAvailability.ready_state(details={
            "geometry_implementation": geometry.implementation_id,
            "vertex_count": len(mesh.data.vertices),
            "mesh_height": bounds.height,
            "preset": IMPLEMENTATION_ID,
            "rig_quality": quality.as_dict(),
            "rig_fit": fit.as_dict(),
        })

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            geometry, mesh, bounds, bones, quality, fit = _prepare(context)
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.RIG,
                implementation_id=IMPLEMENTATION_ID,
                message=f"Cannot prepare Canonical Biped V2 rig: {exc}",
            )

        armature = None
        original_groups = {group.name for group in mesh.vertex_groups}
        original_modifiers = {modifier.name for modifier in mesh.modifiers}
        original_parent = mesh.parent
        original_world = mesh.matrix_world.copy()
        rig_properties = (
            "meshvenn_rig_implementation", "meshvenn_rig_semantics",
            "meshvenn_rig_quality", "meshvenn_rig_fit",
            "meshvenn_rig_skinning_algorithm",
        )
        original_metadata = {key: mesh[key] for key in rig_properties if key in mesh}
        try:
            armature = create_armature(mesh, bones)
            binding_method, max_influences = bind_mesh_deterministic(
                mesh, armature, bones, bounds
            )
            semantic_bones = {spec.name: spec.name for spec in bones}
            metrics = {
                "bone_count": len(bones),
                "deform_bone_count": sum(spec.deform for spec in bones),
                "vertex_count": len(mesh.data.vertices),
                "max_influences_per_vertex": max_influences,
                "fit_confidence": fit.confidence,
                "rig_quality_warning_count": len(quality.warnings),
            }
            output = RigOutput(
                geometry=geometry,
                blender_object=mesh,
                armature_object=armature,
                implementation_id=IMPLEMENTATION_ID,
                semantic_bones=semantic_bones,
                binding_method=binding_method,
                metrics=metrics,
            )
            mesh["meshvenn_rig_implementation"] = IMPLEMENTATION_ID
            mesh["meshvenn_rig_semantics"] = json.dumps(semantic_bones, sort_keys=True)
            mesh["meshvenn_rig_quality"] = json.dumps(quality.as_dict(), sort_keys=True)
            mesh["meshvenn_rig_fit"] = json.dumps(fit.as_dict(), sort_keys=True)
            mesh["meshvenn_rig_skinning_algorithm"] = "regional-envelope-v2"
            armature["meshvenn_rig_implementation"] = IMPLEMENTATION_ID
            context.metadata["rig_object_name"] = armature.name
            context.metadata["rig_binding_method"] = binding_method
            context.metadata["rig_skinning_algorithm"] = "regional-envelope-v2"
            context.metadata["rig_quality"] = quality.as_dict()
            context.metadata["rig_fit"] = fit.as_dict()
            return StageExecutionResult.succeeded(
                stage=PipelineStage.RIG,
                implementation_id=IMPLEMENTATION_ID,
                payload=output,
                message=(
                    f"Canonical Biped V2 created with {len(bones)} bones, "
                    f"{binding_method} skinning and {fit.confidence:.2f} fit confidence."
                ),
                metrics=metrics,
                metadata={
                    "armature_name": armature.name,
                    "mesh_name": mesh.name,
                    "geometry_implementation": geometry.implementation_id,
                    "binding_method": binding_method,
                    "skinning_algorithm": "regional-envelope-v2",
                    "rig_quality": quality.as_dict(),
                    "rig_fit": fit.as_dict(),
                },
            )
        except Exception as exc:
            if armature is not None:
                _remove_new_binding(
                    mesh, original_groups, original_modifiers, original_parent, original_world
                )
                for key in rig_properties:
                    if key in original_metadata:
                        mesh[key] = original_metadata[key]
                    elif key in mesh:
                        del mesh[key]
                data = armature.data
                bpy.data.objects.remove(armature, do_unlink=True)
                if data.users == 0:
                    bpy.data.armatures.remove(data)
            return StageExecutionResult.failed_result(
                stage=PipelineStage.RIG,
                implementation_id=IMPLEMENTATION_ID,
                message=f"Canonical Biped V2 rig failed: {exc}",
            )

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="Canonical Biped V2", icon="ARMATURE_DATA")
        box.label(text="Envelope-guided A/T-pose fit")
        box.label(text="Deterministic regional skinning")
        box.label(text="Best for upright biped characters", icon="INFO")
