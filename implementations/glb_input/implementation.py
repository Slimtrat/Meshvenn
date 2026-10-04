"""Validate a GLB artifact without mutating the Blender scene."""

from __future__ import annotations

import os
from pathlib import Path

from ...core.glb_input_contracts import GLBFileInputOutput
from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ..glb_export.manifest import GLBManifest, inspect_glb


IMPLEMENTATION_ID = "glb-file-v1"
INPUT_PATH_METADATA_KEY = "glb_input_path"


def _inspect_context(context: PipelineContext) -> GLBManifest:
    value = context.metadata.get(INPUT_PATH_METADATA_KEY)
    try:
        raw_path = os.fspath(value)
    except TypeError as exc:
        raise TypeError("Choose a GLB input file.") from exc
    if not str(raw_path).strip():
        raise ValueError("Choose a GLB input file.")
    path = Path(raw_path).expanduser().resolve(strict=False)
    if path.suffix.lower() != ".glb":
        raise ValueError("GLB-first input must use the .glb extension.")
    if not path.is_file():
        raise FileNotFoundError(f"GLB input does not exist: {path}")
    # glTF names are labels, not identifiers; valid source assets may repeat them.
    manifest = inspect_glb(path, require_unique_animation_names=False)
    if manifest.scene_count < 1 or manifest.mesh_count < 1:
        raise ValueError("GLB input must contain at least one scene and one mesh.")
    return manifest


class GLBFileInputImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.INPUT,
        label="GLB File V1",
        description="Validate a glTF 2.0 binary asset as the pipeline source.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "glb-first",
            "gltf-2.0-binary",
            "artifact-integrity",
            "image-independent",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            manifest = _inspect_context(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        details = {
            "path": str(manifest.path),
            "size_bytes": manifest.size_bytes,
            "mesh_count": manifest.mesh_count,
            "skin_count": manifest.skin_count,
            "animation_count": len(manifest.animation_names),
        }
        if manifest.skin_count and not manifest.animation_names:
            return ImplementationAvailability.degraded(
                "The GLB is skinned but contains no animation.", details=details
            )
        return ImplementationAvailability.ready_state(details=details)

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="GLB File V1", icon="FILE_3D")
        settings = getattr(getattr(context, "scene", None), "bpt_settings", None)
        if settings is None:
            box.label(text="Meshvenn settings unavailable", icon="ERROR")
            return
        box.prop(settings, "glb_input_path", text="Source GLB")
        box.label(text="Validated without importing or changing the scene")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            manifest = _inspect_context(context)
            output = GLBFileInputOutput(
                path=manifest.path,
                implementation_id=IMPLEMENTATION_ID,
                size_bytes=manifest.size_bytes,
                sha256=manifest.sha256,
                node_names=manifest.node_names,
                animation_names=manifest.animation_names,
                scene_count=manifest.scene_count,
                mesh_count=manifest.mesh_count,
                skin_count=manifest.skin_count,
                material_count=manifest.material_count,
                metadata={
                    "source": "glb-first",
                    "skin_joint_names": manifest.skin_joint_names,
                    "morph_target_count": manifest.morph_target_count,
                },
            )
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.INPUT,
                implementation_id=IMPLEMENTATION_ID,
                message=f"GLB input validation failed: {exc}",
            )

        context.metadata[INPUT_PATH_METADATA_KEY] = str(output.path)
        context.metadata["glb_input_sha256"] = output.sha256
        context.metadata["glb_input_animation_names"] = output.animation_names
        return StageExecutionResult.succeeded(
            stage=PipelineStage.INPUT,
            implementation_id=IMPLEMENTATION_ID,
            payload=output,
            message=(
                f"Validated GLB with {output.mesh_count} mesh(es), "
                f"{output.skin_count} skin(s) and {len(output.animation_names)} animation(s)."
            ),
            metrics={
                "size_bytes": output.size_bytes,
                "scene_count": output.scene_count,
                "mesh_count": output.mesh_count,
                "skin_count": output.skin_count,
                "material_count": output.material_count,
                "animation_count": len(output.animation_names),
            },
            metadata={"path": str(output.path), "sha256": output.sha256},
        )


__all__ = (
    "GLBFileInputImplementation",
    "IMPLEMENTATION_ID",
    "INPUT_PATH_METADATA_KEY",
)
