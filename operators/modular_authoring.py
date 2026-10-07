"""Whole-face selection tools for exact, source-owned modular declarations."""
import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from ..implementations.glb_export.face_authoring import (
    _read, assign_selected_faces, load_face_ownership, save_face_ownership,
)


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
