from __future__ import annotations

import bpy

from . import operators
from . import properties
from . import ui


MODULES = (
    properties,
    operators,
    ui,
)


def register() -> None:
    for module in MODULES:
        module.register()


def unregister() -> None:
    for module in reversed(MODULES):
        module.unregister()


if __name__ == "__main__":
    register()