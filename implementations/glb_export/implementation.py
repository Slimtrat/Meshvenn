"""Built-in atomic GLB exporter for Geometry, Rig and Motion outputs."""

from __future__ import annotations

from pathlib import Path

from ...core.export_contracts import ExportOutput
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from .blender_export import export_glb
from .planning import (
    OUTPUT_PATH_METADATA_KEY,
    OVERWRITE_METADATA_KEY,
    build_export_plan,
)


IMPLEMENTATION_ID = "glb-export-v1"


class GLBExportImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.EXPORT,
        label="GLB Export V1",
        description="Atomically export the current Geometry, Rig and Motion as glTF 2.0 GLB.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "gltf-2.0-binary",
            "atomic-publish",
            "static-mesh",
            "multi-mesh",
            "canonical-skin",
            "source-skin-preservation",
            "motion-clips",
            "artifact-integrity",
            "source-file-protection",
            "export-roundtrip-verification",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            plan = build_export_plan(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        return ImplementationAvailability.ready_state(details={
            "path": str(plan.path),
            "overwrite_existing": plan.overwrite_existing,
            "object_count": len(plan.objects),
            "rigged": plan.rig is not None,
            "animated": plan.motion is not None,
            "animation_count": len(plan.actions),
        })

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="GLB Export V1", icon="EXPORT")
        settings = getattr(getattr(context, "scene", None), "bpt_settings", None)
        if settings is None:
            warning = box.row()
            warning.alert = True
            warning.label(text="Meshvenn settings unavailable", icon="ERROR")
            return
        box.prop(settings, "export_output_path", text="Output GLB")
        box.prop(settings, "export_overwrite_existing", text="Overwrite Existing")
        box.prop(settings, "export_validate_roundtrip", text="Verify Export by Reimport")
        raw_path = settings.export_output_path.strip()
        if not raw_path:
            warning = box.row()
            warning.alert = True
            warning.label(text="Choose an output .glb file", icon="INFO")
        elif Path(raw_path).suffix.lower() != ".glb":
            warning = box.row()
            warning.alert = True
            warning.label(text="Output must use the .glb extension", icon="ERROR")
        box.label(text="Geometry always; Rig and Motion when enabled")
        box.label(text="Validated temporary file, then atomic publish")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        context.metadata["glb_export_roundtrip"] = None
        try:
            plan = build_export_plan(context)
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.EXPORT,
                implementation_id=IMPLEMENTATION_ID,
                message=f"Cannot prepare GLB export: {exc}",
            )

        try:
            fidelity_report = {}
            manifest = export_glb(plan, fidelity_report=fidelity_report)
            object_names = tuple(obj.name for obj in plan.objects)
            metrics = {
                "size_bytes": manifest.size_bytes,
                "node_count": len(manifest.node_names),
                "scene_count": manifest.scene_count,
                "mesh_count": manifest.mesh_count,
                "skin_count": manifest.skin_count,
                "material_count": manifest.material_count,
                "animation_count": len(manifest.animation_names),
            }
            metadata = {
                "sha256": manifest.sha256,
                "gltf_version": "2.0",
                "overwrite_existing": plan.overwrite_existing,
                "node_names": manifest.node_names,
                "geometry_implementation": plan.geometry.implementation_id,
                "rig_implementation": (
                    plan.rig.implementation_id if plan.rig is not None else None
                ),
                "motion_implementation": (
                    plan.motion.implementation_id if plan.motion is not None else None
                ),
                "roundtrip": fidelity_report or None,
            }
            output = ExportOutput(
                geometry=plan.geometry,
                rig=plan.rig,
                motion=plan.motion,
                implementation_id=IMPLEMENTATION_ID,
                path=manifest.path,
                format="GLB",
                size_bytes=manifest.size_bytes,
                sha256=manifest.sha256,
                object_names=object_names,
                animation_names=manifest.animation_names,
                metrics=metrics,
                metadata=metadata,
            )
            context.metadata["exported_glb_path"] = str(output.path)
            context.metadata["exported_glb_sha256"] = output.sha256
            context.metadata["exported_animation_names"] = output.animation_names
            # Clear evidence from a preceding run when verification is disabled.
            context.metadata["glb_export_roundtrip"] = fidelity_report or None
            return StageExecutionResult.succeeded(
                stage=PipelineStage.EXPORT,
                implementation_id=IMPLEMENTATION_ID,
                payload=output,
                message=(
                    f"Exported GLB ({output.size_bytes} bytes, "
                    f"{len(output.animation_names)} animation(s)) to {output.path}."
                ),
                metrics=metrics,
                metadata=metadata,
            )
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.EXPORT,
                implementation_id=IMPLEMENTATION_ID,
                message=f"GLB export failed: {exc}",
                metadata={
                    "path": str(plan.path),
                    OUTPUT_PATH_METADATA_KEY: str(plan.path),
                    OVERWRITE_METADATA_KEY: plan.overwrite_existing,
                },
            )


__all__ = ("IMPLEMENTATION_ID", "GLBExportImplementation")
