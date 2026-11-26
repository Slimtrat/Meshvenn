import importlib
import bpy
from bpy.props import EnumProperty, FloatProperty, PointerProperty
from .authoring import apply_cloth
from .integration import ClothUVBake, IDENTIFIER, scene_config

_registry = None
_implementation = None


class MVC_Settings(bpy.types.PropertyGroup):
    texture_size: EnumProperty(
        name="Detail map resolution",
        items=[(str(n), str(n), "") for n in (256, 512, 1024, 2048, 4096)],
        default="2048",
    )
    thread_spacing: FloatProperty(
        name="Thread spacing",
        default=0.004,
        min=0.001,
        max=0.025,
        subtype="DISTANCE",
        unit="LENGTH",
    )
    relief: FloatProperty(
        name="Cloth relief",
        default=0.00012,
        min=0.0,
        max=0.001,
        subtype="DISTANCE",
        unit="LENGTH",
    )
    roughness: FloatProperty(name="Fabric roughness", default=0.87, min=0.6, max=1.0)


def connect():
    global _registry, _implementation
    if _registry is not None:
        return
    settings = getattr(bpy.context.scene, "bpt_settings", None)
    if settings is None:
        return
    name = type(settings).__module__.split(".properties.")[0]
    registry = importlib.import_module(
        name + ".core.pipeline_registry"
    ).PIPELINE_REGISTRY
    implementation = ClothUVBake(registry.require("uv-bake-v2"))
    registry.register(implementation)
    _registry = registry
    _implementation = implementation


class MVC_OT_Apply(bpy.types.Operator):
    bl_idname = "meshvenn_cloth.apply"
    bl_label = "Bake cloth surface"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            apply_cloth(context.active_object, scene_config(context.scene))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Portable cloth normal and roughness maps baked")
        return {"FINISHED"}


class MVC_OT_Connect(bpy.types.Operator):
    bl_idname = "meshvenn_cloth.connect"
    bl_label = "Connect Cloth UV Bake"

    def execute(self, context):
        connect()
        if _registry is None:
            self.report({"ERROR"}, "Enable Meshvenn first")
            return {"CANCELLED"}
        return {"FINISHED"}


class MVC_PT_Cloth(bpy.types.Panel):
    bl_label = "Cloth surface"
    bl_idname = "MVC_PT_Cloth"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Meshvenn"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.meshvenn_cloth
        for name in ("texture_size", "thread_spacing", "relief", "roughness"):
            layout.prop(settings, name)
        layout.operator("meshvenn_cloth.apply")
        if _registry is None:
            layout.operator("meshvenn_cloth.connect")
        else:
            layout.label(text="Cloth UV Bake available in MATERIAL")


CLASSES = (MVC_Settings, MVC_OT_Apply, MVC_OT_Connect, MVC_PT_Cloth)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.meshvenn_cloth = PointerProperty(type=MVC_Settings)
    connect()


def unregister():
    global _registry, _implementation
    if _registry is not None and _registry.get(IDENTIFIER) is _implementation:
        _registry.unregister(IDENTIFIER)
    _registry = None
    _implementation = None
    del bpy.types.Scene.meshvenn_cloth
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
