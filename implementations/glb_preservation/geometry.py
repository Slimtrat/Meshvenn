"""GLB Geometry implementation that preserves source character data."""

from __future__ import annotations

import math

import bpy

from ...core.glb_input_contracts import require_glb_file_input
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from .contracts import PreservedGLBGeometryOutput
from .importer import import_preserved_glb


IMPLEMENTATION_ID = "glb-preserved-geometry-v1"
TARGET_EXTENT_METADATA_KEY = "glb_normalized_extent"


def _target_extent(context: PipelineContext) -> float:
    value = float(context.metadata.get(TARGET_EXTENT_METADATA_KEY, 2.0))
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("GLB preserved extent must be finite and greater than zero.")
    return value


class GLBPreservedGeometryImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.GEOMETRY,
        label="GLB Preserved Character Geometry V1",
        description=(
            "Import and normalize a GLB while retaining its meshes, rig, skin and actions."
        ),
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "glb-first",
            "multi-mesh",
            "source-rig-preservation",
            "source-skin-preservation",
            "source-action-preservation",
            "material-preservation",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            source = require_glb_file_input(context)
            extent = _target_extent(context)
            if source.skin_count < 1:
                raise ValueError("Source-preservation route requires a GLB skin.")
            if bpy.context.scene is None:
                raise RuntimeError("No active Blender scene.")
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        return ImplementationAvailability.ready_state(details={
            "path": str(source.path),
            "source_mesh_count": source.mesh_count,
            "source_skin_count": source.skin_count,
            "source_animation_count": len(source.animation_names),
            "normalized_extent": extent,
        })

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="GLB Preserved Character Geometry V1", icon="MESH_DATA")
        settings = getattr(getattr(context, "scene", None), "bpt_settings", None)
        if settings is None:
            box.label(text="Meshvenn settings unavailable", icon="ERROR")
            return
        box.prop(settings, "glb_normalized_extent", text="Normalized Size")
        box.label(text="Keeps source meshes, materials, rig, skin and actions")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            source = require_glb_file_input(context)
            preserved = import_preserved_glb(
                source.path, target_extent=_target_extent(context)
            )
            compatibility = preserved.compatibility
            metrics = {
                "source_mesh_count": len(preserved.mesh_objects),
                "source_vertex_count": preserved.source_vertex_count,
                "source_polygon_count": preserved.source_polygon_count,
                "mesh_object_count": len(preserved.mesh_objects),
                "vertex_count": sum(
                    len(mesh.data.vertices) for mesh in preserved.mesh_objects
                ),
                "polygon_count": sum(
                    len(mesh.data.polygons) for mesh in preserved.mesh_objects
                ),
                "source_action_count": len(preserved.actions),
                "source_bone_count": len(preserved.armature_object.data.bones),
                "normalization_scale": preserved.normalization_scale,
                "source_rig_structural_score": compatibility.structure.structural_score,
                "source_rig_semantic_score": compatibility.semantic_score,
                "target_rig_compatible": compatibility.target_compatible,
            }
            metadata = {
                "source_path": str(source.path),
                "source_sha256": source.sha256,
                "source_rig_profile": preserved.source_profile_id,
                "source_profile_certification": (
                    preserved.source_profile_certification
                ),
                "source_rig_archetype": preserved.source_rig_archetype,
                "source_rig_compatibility": compatibility.as_dict(),
                "source_character_preserved": True,
                "original_dimensions": preserved.original_dimensions,
                "normalized_dimensions": preserved.normalized_dimensions,
            }
            output = PreservedGLBGeometryOutput(
                blender_object=preserved.primary_mesh,
                blender_objects=preserved.mesh_objects,
                source=source,
                projection_space=preserved.projection_space,
                implementation_id=IMPLEMENTATION_ID,
                metrics=metrics,
                metadata=metadata,
                armature_object=preserved.armature_object,
                actions=preserved.actions,
                source_profile_id=preserved.source_profile_id,
                source_profile_certification=preserved.source_profile_certification,
                source_rig_archetype=preserved.source_rig_archetype,
                semantic_bones=preserved.semantic_bones,
            )
            for mesh in preserved.mesh_objects:
                mesh["meshvenn_geometry_implementation"] = IMPLEMENTATION_ID
                mesh["meshvenn_glb_source_sha256"] = source.sha256
            preserved.armature_object["meshvenn_source_rig_profile"] = (
                preserved.source_profile_id
            )
            context.metadata.update({
                "glb_source_rig_profile": preserved.source_profile_id,
                "glb_source_profile_certification": (
                    preserved.source_profile_certification
                ),
                "glb_source_rig_archetype": preserved.source_rig_archetype,
                "glb_source_motion_profile_recognized": True,
                "glb_source_motion_compatible": bool(preserved.actions),
                "glb_target_rig": compatibility.target_rig,
                "glb_target_rig_compatible": compatibility.target_compatible,
                "glb_rig_structural_score": compatibility.structure.structural_score,
                "glb_rig_semantic_score": compatibility.semantic_score,
                "glb_rig_compatibility_reasons": compatibility.reasons,
                "glb_character_route": "preserve-source",
            })
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.GEOMETRY,
                implementation_id=IMPLEMENTATION_ID,
                message=f"GLB source preservation failed: {exc}",
            )

        return StageExecutionResult.succeeded(
            stage=PipelineStage.GEOMETRY,
            implementation_id=IMPLEMENTATION_ID,
            payload=output,
            message=(
                f"Preserved {len(preserved.mesh_objects)} mesh(es), "
                f"{len(preserved.armature_object.data.bones)} bones and "
                f"{len(preserved.actions)} action(s) from "
                f"{preserved.source_profile_id}."
            ),
            metrics=metrics,
            metadata=metadata,
        )


__all__ = ("GLBPreservedGeometryImplementation", "IMPLEMENTATION_ID")
