"""Independent registration and safe removal of this extension's overlays."""
import bpy
from bpy.app.handlers import persistent
from bpy.props import PointerProperty

from . import drawing,operators,properties,ui

CLASSES=(*properties.CLASSES,*operators.CLASSES,drawing.MVSK_OT_Draw,*ui.CLASSES)


@persistent
def _before_load(_):
    drawing.cleanup()


def register():
    registered=[]
    try:
        for cls in CLASSES:bpy.utils.register_class(cls);registered.append(cls)
        bpy.types.Scene.mvsketch=PointerProperty(type=properties.MVSK_Settings)
        bpy.app.handlers.load_pre.append(_before_load)
    except BaseException:
        for cls in reversed(registered):bpy.utils.unregister_class(cls)
        raise


def unregister():
    drawing.cleanup()
    if _before_load in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(_before_load)
    if hasattr(bpy.types.Scene,'mvsketch'):del bpy.types.Scene.mvsketch
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
