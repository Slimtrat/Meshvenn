"""Independent registration and safe removal of this extension's overlays."""
import bpy
from bpy.props import PointerProperty

from . import drawing,operators,properties,ui

CLASSES=(*properties.CLASSES,*operators.CLASSES,drawing.MVSK_OT_Draw,*ui.CLASSES)


def register():
    registered=[]
    try:
        for cls in CLASSES:bpy.utils.register_class(cls);registered.append(cls)
        bpy.types.Scene.mvsketch=PointerProperty(type=properties.MVSK_Settings)
    except BaseException:
        for cls in reversed(registered):bpy.utils.unregister_class(cls)
        raise


def unregister():
    drawing.cleanup()
    if hasattr(bpy.types.Scene,'mvsketch'):del bpy.types.Scene.mvsketch
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
