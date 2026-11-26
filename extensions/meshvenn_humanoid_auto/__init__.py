"""Optional Blender extension; the core engine never imports its quality policy."""


def register():
    from . import registration

    registration.register()


def unregister():
    from . import registration

    registration.unregister()
