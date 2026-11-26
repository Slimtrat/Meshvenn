from pathlib import Path
import importlib, tempfile
import bpy
from bpy.props import BoolProperty, FloatProperty, PointerProperty, StringProperty
from meshvenn_humanoid.integration import Binding
from meshvenn_humanoid.blender.supervisor import SubprocessSupervisor

_binding = None


class MVH_Settings(bpy.types.PropertyGroup):
    enabled: BoolProperty(name="Automatic humanoid checks", default=True)
    workspace: StringProperty(name="Reports folder", subtype="DIR_PATH", default="")
    max_seconds: FloatProperty(
        name="Time budget", default=60.0, min=5.0, max=120.0, subtype="TIME"
    )


def supervisor(context, rig):
    settings = context.scene.meshvenn_humanoid
    if not settings.enabled:
        return dict(status="disabled")
    name = type(context.scene.bpt_settings).__module__.split(".properties.")[0]
    engine = importlib.import_module(name)
    root = Path(engine.__file__).resolve().parent
    workspace = (
        Path(bpy.path.abspath(settings.workspace))
        if settings.workspace
        else Path(tempfile.gettempdir()) / "meshvenn-humanoid"
    )
    result = SubprocessSupervisor(root, workspace, max_seconds=settings.max_seconds)(
        context, rig
    )
    context.scene["meshvenn_humanoid_last_report"] = result.get("report_path", "")
    return result


def connect():
    global _binding
    if _binding is not None:
        return
    settings = getattr(bpy.context.scene, "bpt_settings", None)
    if settings is None:
        return
    name = type(settings).__module__.split(".properties.")[0]
    registry = importlib.import_module(
        name + ".core.pipeline_registry"
    ).PIPELINE_REGISTRY
    _binding = Binding(registry, supervisor)


class MVH_OT_Connect(bpy.types.Operator):
    bl_idname = "meshvenn_humanoid.connect"
    bl_label = "Connect humanoid quality loop"

    def execute(self, context):
        connect()
        if _binding is None:
            self.report({"ERROR"}, "Enable Meshvenn first")
            return {"CANCELLED"}
        return {"FINISHED"}


class MVH_PT_Quality(bpy.types.Panel):
    bl_label = "Humanoid quality loop"
    bl_idname = "MVH_PT_Quality"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Meshvenn"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.meshvenn_humanoid
        layout.prop(settings, "enabled")
        layout.prop(settings, "workspace")
        layout.prop(settings, "max_seconds")
        if _binding is None:
            layout.operator("meshvenn_humanoid.connect")
        else:
            layout.label(text="Runs automatically after Canonical Rig V2")
        path = context.scene.get("meshvenn_humanoid_last_report", "")
        if path:
            layout.label(text="Latest report: " + Path(path).parent.parent.name[:24])


CLASSES = (MVH_Settings, MVH_OT_Connect, MVH_PT_Quality)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.meshvenn_humanoid = PointerProperty(type=MVH_Settings)
    connect()


def unregister():
    global _binding
    if _binding is not None:
        _binding.close()
        _binding = None
    del bpy.types.Scene.meshvenn_humanoid
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
