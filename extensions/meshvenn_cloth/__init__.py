"""Optional portable cloth finishing, independent of the Meshvenn engine."""


def register():
    from . import registration

    registration.register()


def unregister():
    from . import registration

    registration.unregister()
