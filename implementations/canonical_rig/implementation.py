"""Canonical biped rig engine for reconstructed MeshVenn surfaces."""

from __future__ import annotations

import json

import bpy

from ...core.canonical_rig import bounds_from_vertices, fit_canonical_biped
from ...core.geometry_contracts import require_geometry_surface_output
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.rig_quality import assess_biped_geometry
from ...core.rig_contracts import RigOutput
from .binding import _remove_new_binding, bind_mesh, create_armature

IMPLEMENTATION_ID = "canonical-biped-v1"


def _require_mesh(context: PipelineContext):
    geometry = require_geometry_surface_output(context)
    mesh = geometry.blender_object
    if not isinstance(mesh, bpy.types.Object) or mesh.type != "MESH":
        raise TypeError("Canonical Biped requires a Blender mesh object.")
    if mesh.data is None or not mesh.data.vertices or not mesh.data.polygons:
        raise ValueError("Canonical Biped requires a nonempty surface mesh.")
    if bpy.context.mode != "OBJECT":
        raise RuntimeError("Leave Edit or Pose mode before generating a rig.")
    if mesh.parent is not None or any(mod.type == "ARMATURE" for mod in mesh.modifiers):
        raise ValueError("This mesh already has a rig; regenerate geometry or remove the existing rig first.")
    return geometry, mesh


def _prepare(context: PipelineContext):
    geometry, mesh = _require_mesh(context)
    bounds = bounds_from_vertices(vertex.co for vertex in mesh.data.vertices)
    quality = assess_biped_geometry((vertex.co for vertex in mesh.data.vertices), bounds)
    bones = fit_canonical_biped(bounds)
    existing = {group.name for group in mesh.vertex_groups}
    conflicts = existing.intersection(spec.name for spec in bones)
    if conflicts:
        raise ValueError(
            "Existing vertex groups conflict with Canonical Biped bones: "
            + ", ".join(sorted(conflicts))
        )
    return geometry, mesh, bounds, bones, quality


class CanonicalRigImplementation:
    """Fits a standard biped hierarchy, then binds the mesh to its armature."""

    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.RIG,
        label="Canonical Biped V1",
        description="Fit a standard biped armature and skin the reconstructed mesh.",
        version="1",
        experimental=True,
        supports_headless=True,
        capabilities=("canonical-biped", "semantic-bones", "automatic-skinning", "glb-ready"),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            geometry, mesh, bounds, _, quality = _prepare(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        return ImplementationAvailability.ready_state(details={
            "geometry_implementation": geometry.implementation_id,
            "vertex_count": len(mesh.data.vertices),
            "mesh_height": bounds.height,
            "preset": "canonical-biped-v1",
            "rig_quality": quality.as_dict(),
        })

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            geometry, mesh, _, bones, quality = _prepare(context)
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.RIG,
                implementation_id=IMPLEMENTATION_ID,
                message=f"Cannot prepare Canonical Biped rig: {exc}",
            )

        armature = None
        original_groups = {group.name for group in mesh.vertex_groups}
        original_modifiers = {modifier.name for modifier in mesh.modifiers}
        original_parent = mesh.parent
        original_world = mesh.matrix_world.copy()
        rig_properties = ("meshvenn_rig_implementation", "meshvenn_rig_semantics", "meshvenn_rig_quality")
        original_metadata = {key: mesh[key] for key in rig_properties if key in mesh}
        try:
            armature = create_armature(mesh, bones)
            binding_method, max_influences = bind_mesh(mesh, armature, bones)
            semantic_bones = {spec.name: spec.name for spec in bones}
            metrics = {
                "bone_count": len(bones),
                "deform_bone_count": sum(spec.deform for spec in bones),
                "vertex_count": len(mesh.data.vertices),
                "max_influences_per_vertex": max_influences,
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
            armature["meshvenn_rig_implementation"] = IMPLEMENTATION_ID
            context.metadata["rig_object_name"] = armature.name
            context.metadata["rig_binding_method"] = binding_method
            context.metadata["rig_quality"] = quality.as_dict()
            warning_suffix = (
                f" Geometry warnings: {', '.join(quality.warnings)}."
                if quality.warnings else ""
            )
            return StageExecutionResult.succeeded(
                stage=PipelineStage.RIG,
                implementation_id=IMPLEMENTATION_ID,
                payload=output,
                message=f"Canonical rig created with {len(bones)} bones and {binding_method} skinning.{warning_suffix}",
                metrics=metrics,
                metadata={
                    "armature_name": armature.name,
                    "mesh_name": mesh.name,
                    "geometry_implementation": geometry.implementation_id,
                    "binding_method": binding_method,
                    "rig_quality": quality.as_dict(),
                },
            )
        except Exception as exc:
            if armature is not None:
                _remove_new_binding(mesh, original_groups, original_modifiers, original_parent, original_world)
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
                message=f"Canonical Biped rig failed: {exc}",
            )

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="Canonical Biped V1", icon="ARMATURE_DATA")
        box.label(text="Fits an A-pose skeleton to mesh bounds")
        box.label(text="Automatic skinning with deterministic fallback")
        box.label(text="Best for upright biped characters", icon="INFO")
