"""Export authored originals independently of the reconstruction pipeline."""

import time

from bpy.types import Operator
from bpy.props import BoolProperty, StringProperty

from ..core.pipeline_contracts import PipelinePlan, PipelineStage, PipelineStageSelection
from ..core.pipeline_runner import PipelineExecutionReport, StageRunRecord
from ..implementations.glb_export.implementation import GLBExportImplementation, IMPLEMENTATION_ID
from ..implementations.glb_export.modular_source import context_from_authored_scene
from .runtime_state import _store_pipeline_runtime, clear_pipeline_runtime_state


class BPT_OT_ExportExistingModularSource(Operator):
    bl_idname = "bpt.export_existing_modular_source"
    bl_label = "Export Authoritative Source (No Reconstruction)"
    bl_description = (
        "Re-export the original objects named by the authoring JSON with their saved native rig and Actions; "
        "do not reconstruct geometry or export edits to derived preview copies"
    )
    initialize_static_source: BoolProperty(
        name="Initialize Old Static Source", default=False,
        description="Explicit first export of an old unanimated native V2 source; never infer or drop clips",
    )
    binding_method: StringProperty(name="Declared Native Binding", default="")

    @classmethod
    def poll(cls, context):
        return context.scene is not None and getattr(context.scene, "bpt_settings", None) is not None

    def execute(self, context):
        clear_pipeline_runtime_state(context.scene)
        try:
            prepared = context_from_authored_scene(
                context.scene, initialize_static_source=self.initialize_static_source,
                binding_method=self.binding_method if self.initialize_static_source else None,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"Cannot re-export authoritative modular source: {exc}")
            return {"CANCELLED"}
        selection = PipelineStageSelection(PipelineStage.EXPORT, IMPLEMENTATION_ID)
        started = time.perf_counter()
        try:
            result = GLBExportImplementation().execute(prepared)
        finally:
            prepared.prepared_modular_source.discard()
        elapsed = time.perf_counter() - started
        if result.success:
            prepared.set_output(PipelineStage.EXPORT, result.payload)
        report = PipelineExecutionReport(PipelinePlan((selection,)), prepared,
                                         (StageRunRecord(selection, result, elapsed),), (), elapsed, result.failed)
        _store_pipeline_runtime(context.scene, prepared, report)
        if not result.success:
            self.report({"ERROR"}, result.message)
            return {"CANCELLED"}
        self.report({"INFO"}, result.message + " Authoritative source preserved; no reconstruction.")
        return {"FINISHED"}
