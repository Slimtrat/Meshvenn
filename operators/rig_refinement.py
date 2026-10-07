"""Explicit, undoable native source skin refinement."""
import bpy

from ..implementations.canonical_rig_v2.head_refinement import refine_head_weights


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
            mesh = context.active_object
            for obj in context.scene.objects:
                if obj.type == "MESH" and obj.get("meshvenn_source_mesh") == mesh.name:
                    obj.hide_set(True)
                    obj.hide_render = True
            mesh.hide_set(False)
            mesh.hide_render = False
        except Exception as exc:
            self.report({"WARNING"}, f"Weights applied; preview visibility could not be refreshed: {exc}")
        self.report({"INFO"}, f"Head isolated: {result['changed_vertex_count']} vertices; native rest rig and textures unchanged")
        return {"FINISHED"}
