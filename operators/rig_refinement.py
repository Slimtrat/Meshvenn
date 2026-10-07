"""Explicit, undoable native source skin refinement."""
import bpy

from ..implementations.canonical_rig_v2.head_refinement import refine_head_weights
from ..implementations.canonical_rig_v2.owned_refinement import refine_owned_skin
from ..implementations.glb_export.face_authoring import _read


def _show_authority(context):
    mesh = context.active_object
    for obj in context.scene.objects:
        if obj.type == "MESH" and obj.get("meshvenn_source_mesh") == mesh.name:
            obj.hide_set(True)
            obj.hide_render = True
    mesh.hide_set(False)
    mesh.hide_render = False


class BPT_OT_RefineHeadWeights(bpy.types.Operator):
    bl_idname = "bpt.refine_head_weights"
    bl_label = "Isolate Head Weights"
    bl_description = "Refine selected canonical source weights from its neck surface; keep native joints and textures"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        mesh = context.active_object
        return bool(mesh and mesh.type == "MESH" and mesh.mode == "OBJECT"
                    and mesh.get("meshvenn_rig_implementation") == "canonical-biped-v2"
                    and mesh.get("meshvenn_rig_skinning_algorithm") != "regional-fitted-v2-head-isolation"
                    and "meshvenn_owned_skin_refinement" not in mesh
                    and "meshvenn_source_mesh" not in mesh)

    def execute(self, context):
        try:
            result = refine_head_weights(context.active_object)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        # Saved modular region copies are disposable previews with old weights.
        # Show the edited authority, never leave stale copies looking current.
        try:
            _show_authority(context)
        except Exception as exc:
            self.report({"WARNING"}, f"Weights applied; preview visibility could not be refreshed: {exc}")
        self.report({"INFO"}, f"Head isolated: {result['changed_vertex_count']} vertices; native rest rig and textures unchanged")
        return {"FINISHED"}


class BPT_OT_RefineOwnedSkin(bpy.types.Operator):
    bl_idname = "bpt.refine_owned_skin"
    bl_label = "Refine Authored Body Skin"
    bl_description = "Isolate torso and blend attachment collars using explicit modular face ownership; retain rest joints and textures"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        mesh = context.active_object
        return bool(mesh and mesh.type == "MESH" and mesh.mode == "OBJECT"
                    and mesh.get("meshvenn_rig_implementation") == "canonical-biped-v2"
                    and "meshvenn_owned_skin_refinement" not in mesh
                    and "meshvenn_source_mesh" not in mesh)

    def execute(self, context):
        try:
            path = context.scene.bpt_settings.export_modular_manifest_path
            if not path:
                raise ValueError("Select an explicit modular authoring declaration first.")
            result = refine_owned_skin(context.active_object, _read(bpy.path.abspath(path)))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        try:
            _show_authority(context)
        except Exception as exc:
            self.report({"WARNING"}, f"Weights applied; preview visibility could not be refreshed: {exc}")
        self.report({"INFO"}, f"Authored body skin refined: {result['changed_vertex_count']} vertices; native rig and textures unchanged")
        return {"FINISHED"}
