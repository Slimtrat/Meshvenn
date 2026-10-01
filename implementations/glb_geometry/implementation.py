"""Convert a validated GLB input into neutral normalized pipeline geometry."""

from __future__ import annotations

import math

import bpy

from ...core.geometry_contracts import GeometrySurfaceOutput
from ...core.glb_input_contracts import require_glb_file_input
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from .normalization import import_and_normalize_glb


IMPLEMENTATION_ID = "glb-normalized-geometry-v1"
TARGET_EXTENT_METADATA_KEY = "glb_normalized_extent"


def _target_extent(context: PipelineContext) -> float:
    value = float(context.metadata.get(TARGET_EXTENT_METADATA_KEY, 2.0))
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("GLB normalized extent must be finite and greater than zero.")
    return value


class GLBNormalizedGeometryImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.GEOMETRY,
        label="GLB Normalized Geometry V1",
        description="Import, merge and normalize a GLB into neutral rig-ready geometry.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "glb-first",
            "multi-mesh",
            "transform-baking",
            "rig-neutralization",
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
        box.label(text="GLB Normalized Geometry V1", icon="MESH_DATA")
        settings = getattr(getattr(context, "scene", None), "bpt_settings", None)
        if settings is None:
            box.label(text="Meshvenn settings unavailable", icon="ERROR")
            return
        box.prop(settings, "glb_normalized_extent", text="Normalized Size")
        box.label(text="Merges meshes, bakes transforms and removes source rigging")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            source = require_glb_file_input(context)
            extent = _target_extent(context)
            normalized = import_and_normalize_glb(
                str(source.path), target_extent=extent
            )
            evidence = normalized.source_rig
            metrics = {
                "source_mesh_count": normalized.source_mesh_count,
                "source_vertex_count": normalized.source_vertex_count,
                "source_polygon_count": normalized.source_polygon_count,
                "vertex_count": len(normalized.mesh_object.data.vertices),
                "polygon_count": len(normalized.mesh_object.data.polygons),
                "normalization_scale": normalized.normalization_scale,
                "source_armature_count": evidence.armature_count,
                "source_action_count": evidence.action_count,
                "source_motion_compatible": evidence.motion_compatible,
                "source_profile_certification": evidence.profile_certification,
            }
            metadata = {
                "source_path": str(source.path),
                "source_sha256": source.sha256,
                "source_rig_profile": evidence.supported_profile,
                "source_profile_certification": evidence.profile_certification,
                "source_motion_compatible": evidence.motion_compatible,
                "original_dimensions": normalized.original_dimensions,
                "normalized_dimensions": normalized.normalized_dimensions,
            }
            output = GeometrySurfaceOutput(
                blender_object=normalized.mesh_object,
                source=source,
                projection_space=normalized.projection_space,
                implementation_id=IMPLEMENTATION_ID,
                metrics=metrics,
                metadata=metadata,
            )
            normalized.mesh_object["meshvenn_geometry_implementation"] = IMPLEMENTATION_ID
            normalized.mesh_object["meshvenn_glb_source_sha256"] = source.sha256
            context.metadata["glb_source_rig_profile"] = evidence.supported_profile
            context.metadata["glb_source_profile_certification"] = (
                evidence.profile_certification
            )
            context.metadata["glb_source_motion_compatible"] = evidence.motion_compatible
            if evidence.motion_compatible and not str(
                context.metadata.get("motion_source_path", "")
            ).strip():
                context.metadata["motion_source_path"] = str(source.path)
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.GEOMETRY,
                implementation_id=IMPLEMENTATION_ID,
                message=f"GLB geometry normalization failed: {exc}",
            )

        return StageExecutionResult.succeeded(
            stage=PipelineStage.GEOMETRY,
            implementation_id=IMPLEMENTATION_ID,
            payload=output,
            message=(
                f"Normalized {normalized.source_mesh_count} GLB mesh(es) into "
                f"{metrics['vertex_count']} vertices; source Motion compatibility: "
                f"{'yes' if evidence.motion_compatible else 'no'}."
            ),
            metrics=metrics,
            metadata=metadata,
        )


__all__ = (
    "GLBNormalizedGeometryImplementation",
    "IMPLEMENTATION_ID",
    "TARGET_EXTENT_METADATA_KEY",
)
