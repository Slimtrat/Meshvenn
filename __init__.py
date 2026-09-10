# __init__.py

from __future__ import annotations

from . import properties
from . import implementations
from . import operators
from . import ui


# ---------------------------------------------------------
# Blender module lifecycle
#
# Registration order is intentional:
#
#     properties
#         ↓
#     implementations
#         ↓
#     operators
#         ↓
#     ui
#
# properties:
#     creates Scene.bpt_settings and pipeline persistence.
#
# implementations:
#     populates PIPELINE_REGISTRY with built-in adapters.
#
# operators:
#     may resolve and execute registered implementations.
#
# ui:
#     may inspect registry descriptors and availability.
#
# Unregistration happens in reverse order.
# ---------------------------------------------------------

MODULES = (
    properties,
    implementations,
    operators,
    ui,
)


def register() -> None:
    for module in MODULES:
        module.register()


def unregister() -> None:
    for module in reversed(
        MODULES
    ):
        module.unregister()


if __name__ == "__main__":
    register()