"""Independent Blender authoring extension; Meshvenn's engine is optional."""


def register():
    from . import registration
    registration.register()


def unregister():
    from . import registration
    registration.unregister()
