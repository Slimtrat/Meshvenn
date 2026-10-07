"""Whole-face selection tools for exact, source-owned modular declarations."""
import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from ..implementations.glb_export.face_authoring import (
    _read, assign_selected_faces, load_face_ownership, save_face_ownership,
)
from ..implementations.authored_source import prepare_authored_source
from .runtime import get_last_pipeline_context


def draw_modular_authoring_controls(layout):
    """Authoring owns editing and explicit preparation; export consumes it."""
    editing = layout.column(align=True)
    editing.operator("bpt.load_modular_face_ownership", text="Load Face Ownership", icon="IMPORT")
    editing.operator("bpt.assign_modular_faces", text="Assign Selected Faces", icon="FACESEL")
    editing.operator("bpt.save_modular_face_ownership", text="Save Face Ownership", icon="FILE_TICK")
    editing.operator("bpt.prepare_modular_source", text="Prepare Current Modular Source", icon="CHECKMARK")
    initial = layout.operator("bpt.export_existing_modular_source", text="Initialize Old Static V2 Source (No Rebuild)", icon="FILE_REFRESH")
    initial.initialize_static_source = True
    initial.binding_method = "canonical-envelope-v2"
    layout.label(text="Initialization explicitly declares no clips; animated sources are refused")
    layout.label(text="JSON originals are authoritative; preview edits are not exported", icon="INFO")


class BPT_OT_PrepareModularSource(Operator):
    bl_idname = "bpt.prepare_modular_source"
    bl_label = "Prepare Current Modular Source"
    bl_description = "Explicitly validate current mesh, native rig, regions, sockets and exact actions before export"
    replace_existing: BoolProperty(name="Replace Existing Preparation / Action Catalogue", default=False)

    @classmethod
    def poll(cls, context):
        return (context.scene is not None and getattr(context.scene, "bpt_settings", None) is not None
                and get_last_pipeline_context(context.scene) is not None)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        pipeline = get_last_pipeline_context(context.scene)
        settings = context.scene.bpt_settings
        previous_metadata = dict(pipeline.metadata)
        try:
            if not settings.export_modular_character or not settings.export_modular_manifest_path.strip():
                raise ValueError("Enable Modular Character and select its authoring JSON first.")
            pipeline.metadata.pop("export_modular_spec", None)
            pipeline.metadata.update({"export_modular_character": True,
                "export_modular_manifest_path": bpy.path.abspath(settings.export_modular_manifest_path),
                "export_output_path": bpy.path.abspath(settings.export_output_path),
                "export_overwrite_existing": settings.export_overwrite_existing})
            prepare_authored_source(pipeline, replace_existing=self.replace_existing)
        except Exception as exc:
            pipeline.metadata.clear()
            pipeline.metadata.update(previous_metadata)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Editable modular authority prepared. Export will validate and publish it without rebuilding.")
        return {"FINISHED"}


class _FaceAuthoringOperator:
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.scene is not None and getattr(context.scene, "bpt_settings", None) is not None
                and context.object is not None and context.object.type == "MESH")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def path(self, context):
        raw = context.scene.bpt_settings.export_modular_manifest_path
        if not raw.strip():
            raise ValueError("Select the source's Modular Authoring JSON first.")
        return bpy.path.abspath(raw)


class BPT_OT_LoadModularFaceOwnership(_FaceAuthoringOperator, Operator):
    bl_idname = "bpt.load_modular_face_ownership"
    bl_label = "Load Authored Face Ownership"
    bl_description = "Load hash-matching declared regions into an editable face attribute; never infer from weights"
    replace_existing: BoolProperty(name="Replace Existing Face Edits", default=False)

    def execute(self, context):
        try:
            load_face_ownership(context.object, _read(self.path(context)), replace_existing=self.replace_existing)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Exact face ownership loaded; select whole faces to edit.")
        return {"FINISHED"}


class BPT_OT_AssignModularFaces(_FaceAuthoringOperator, Operator):
    bl_idname = "bpt.assign_modular_faces"
    bl_label = "Assign Selected Faces to Region"
    bl_description = "Assign visible selected whole faces to one declared region; preserve geometry, UVs and skin"
    region_id: StringProperty(name="Declared Region ID", default="body-core")

    def execute(self, context):
        try:
            count = assign_selected_faces(context.object, self.region_id)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"{count} whole faces assigned to {self.region_id}.")
        return {"FINISHED"}


class BPT_OT_SaveModularFaceOwnership(_FaceAuthoringOperator, Operator):
    bl_idname = "bpt.save_modular_face_ownership"
    bl_label = "Save Authored Face Ownership"
    bl_description = "Validate complete face attribution and atomically save JSON; keep current socket TRS declarations"
    overwrite: BoolProperty(name="Overwrite Existing JSON", default=False)

    def execute(self, context):
        try:
            path = self.path(context)
            save_face_ownership(context.object, path, path, overwrite=self.overwrite)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Complete face ownership saved; use No Rebuild to export.")
        return {"FINISHED"}
