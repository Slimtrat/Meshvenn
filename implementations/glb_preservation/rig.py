"""RIG stage that exposes a preserved GLB source rig without regeneration."""

from __future__ import annotations

from typing import Any

import bpy

from ...core.pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineStage,
    StageExecutionResult,
)
from ...core.rig_contracts import RigOutput
from .contracts import PreservedGLBGeometryOutput, require_preserved_geometry


IMPLEMENTATION_ID = "glb-source-rig-v1"


def _require_geometry(context: PipelineContext) -> PreservedGLBGeometryOutput:
    geometry = require_preserved_geometry(context.require_output(PipelineStage.GEOMETRY))
    armature = geometry.armature_object
    if not isinstance(armature, bpy.types.Object) or armature.type != "ARMATURE":
        raise TypeError("Preserved source rig requires a Blender armature.")
    if bpy.data.objects.get(armature.name) is not armature:
        raise ValueError("Preserved source armature is no longer available.")
    names = set(armature.data.bones.keys())
    missing = sorted(set(geometry.semantic_bones.values()) - names)
    if missing:
        raise ValueError("Preserved source rig lost semantic bones: " + ", ".join(missing))
    return geometry


def _bound_to(mesh: Any, armature: Any) -> bool:
    if any(
        modifier.type == "ARMATURE" and modifier.object is armature
        for modifier in mesh.modifiers
    ):
        return True
    parent = mesh.parent
    while parent is not None:
        if parent is armature:
            return True
        parent = parent.parent
    return False


def _max_influences(geometry: PreservedGLBGeometryOutput) -> int:
    maximum = 0
    for mesh in geometry.blender_objects:
        maximum = max(
            maximum,
            max((len(vertex.groups) for vertex in mesh.data.vertices), default=0),
        )
        if _bound_to(mesh, geometry.armature_object):
            maximum = max(maximum, 1)
    return maximum


class GLBSourceRigImplementation:
    _descriptor = ImplementationDescriptor(
        identifier=IMPLEMENTATION_ID,
        stage=PipelineStage.RIG,
        label="GLB Source Rig Preservation V1",
        description="Expose the imported GLB rig and skin without rebuilding them.",
        version="1",
        experimental=False,
        supports_headless=True,
        capabilities=(
            "source-rig-preservation",
            "source-skin-preservation",
            "humanoid",
            "quadruped",
            "glb-ready",
        ),
    )

    @property
    def descriptor(self) -> ImplementationDescriptor:
        return self._descriptor

    def availability(self, context: PipelineContext) -> ImplementationAvailability:
        try:
            geometry = _require_geometry(context)
        except Exception as exc:
            return ImplementationAvailability.unavailable(str(exc))
        return ImplementationAvailability.ready_state(details={
            "profile": geometry.source_profile_id,
            "archetype": geometry.source_rig_archetype,
            "mesh_count": len(geometry.blender_objects),
            "bone_count": len(geometry.armature_object.data.bones),
        })

    def draw_settings(self, layout, context) -> None:
        box = layout.box()
        box.label(text="GLB Source Rig Preservation V1", icon="ARMATURE_DATA")
        box.label(text="Keeps the imported hierarchy and skin weights unchanged")

    def execute(self, context: PipelineContext) -> StageExecutionResult:
        try:
            geometry = _require_geometry(context)
            armature = geometry.armature_object
            bound_meshes = tuple(
                mesh for mesh in geometry.blender_objects if _bound_to(mesh, armature)
            )
            if not bound_meshes:
                raise ValueError("No preserved mesh is bound to the source armature.")
            metrics = {
                "bone_count": len(armature.data.bones),
                "semantic_bone_count": len(geometry.semantic_bones),
                "mesh_count": len(geometry.blender_objects),
                "bound_mesh_count": len(bound_meshes),
                "max_influences_per_vertex": _max_influences(geometry),
                "source_rig_preserved": True,
            }
            output = RigOutput(
                geometry=geometry,
                blender_object=geometry.blender_object,
                armature_object=armature,
                implementation_id=IMPLEMENTATION_ID,
                semantic_bones=geometry.semantic_bones,
                binding_method="source-preserved",
                metrics=metrics,
            )
            context.metadata.update({
                "rig_object_name": armature.name,
                "rig_binding_method": "source-preserved",
                "rig_source_profile": geometry.source_profile_id,
                "rig_source_archetype": geometry.source_rig_archetype,
            })
        except Exception as exc:
            return StageExecutionResult.failed_result(
                stage=PipelineStage.RIG,
                implementation_id=IMPLEMENTATION_ID,
                message=f"Cannot expose preserved GLB rig: {exc}",
            )
        return StageExecutionResult.succeeded(
            stage=PipelineStage.RIG,
            implementation_id=IMPLEMENTATION_ID,
            payload=output,
            message=(
                f"Preserved source rig with {metrics['bone_count']} bones across "
                f"{metrics['bound_mesh_count']} bound mesh(es)."
            ),
            metrics=metrics,
            metadata={
                "source_profile": geometry.source_profile_id,
                "source_archetype": geometry.source_rig_archetype,
                "armature_name": armature.name,
            },
        )


__all__ = ("GLBSourceRigImplementation", "IMPLEMENTATION_ID")
