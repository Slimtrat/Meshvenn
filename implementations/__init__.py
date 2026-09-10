from __future__ import annotations

from collections.abc import (
    Callable,
)

from ..core.pipeline_contracts import (
    PipelineImplementation,
)
from ..core.pipeline_registry import (
    PIPELINE_REGISTRY,
)


# ---------------------------------------------------------
# Built-in implementation imports
#
# These modules are the adapters around Meshvenn's current
# production pipeline.
#
# Do not move algorithmic code here:
#
#     core/
#         owns algorithms
#
#     implementations/
#         adapts algorithms to PipelineImplementation
# ---------------------------------------------------------

from .projection_images import (
    ProjectionImagesImplementation,
)
from .native_visual_hull import (
    NativeVisualHullImplementation,
)
from .projected_color import (
    ProjectedColorImplementation,
)


# ---------------------------------------------------------
# Types
# ---------------------------------------------------------

ImplementationFactory = Callable[
    [],
    PipelineImplementation,
]


# ---------------------------------------------------------
# Built-in catalog
# ---------------------------------------------------------

BUILTIN_IMPLEMENTATION_FACTORIES: tuple[
    ImplementationFactory,
    ...
] = (
    ProjectionImagesImplementation,
    NativeVisualHullImplementation,
    ProjectedColorImplementation,
)


# ---------------------------------------------------------
# Registration state
# ---------------------------------------------------------

_registered_implementation_ids: list[
    str
] = []


# ---------------------------------------------------------
# Registration
# ---------------------------------------------------------

def register_builtin_implementations(
    *,
    replace: bool = True,
) -> tuple[
    PipelineImplementation,
    ...
]:
    """
    Instantiate and register every built-in Meshvenn
    pipeline implementation.

    `replace=True` is intentional for Blender development.

    Reloading the add-on recreates Python classes while the
    global registry module may remain alive depending on how
    Blender performs the reload.

    Stable implementation ids therefore remain the source of
    truth.

    Current built-ins:

        INPUT
            projection-images

        GEOMETRY
            native-visual-hull

        MATERIAL
            projected-color-v1.2

    RIG and EXPORT intentionally have no implementation yet.
    The general pipeline supports them already; concrete
    implementations can be added independently later.
    """

    registered: list[
        PipelineImplementation
    ] = []

    current_ids: list[
        str
    ] = []

    for factory in (
        BUILTIN_IMPLEMENTATION_FACTORIES
    ):
        implementation = (
            factory()
        )

        descriptor = (
            implementation
            .descriptor
        )

        PIPELINE_REGISTRY.register(
            implementation,
            default=True,
            replace=replace,
        )

        registered.append(
            implementation
        )

        current_ids.append(
            descriptor.identifier
        )

    # -----------------------------------------------------
    # Remove ids remembered from a previous bootstrap which
    # are no longer part of the built-in catalog.
    #
    # This matters during development:
    #
    #     projected-color-v1.2
    #         ↓ rename
    #     uv-bake-v2
    #
    # Without cleanup, a stale implementation could remain
    # visible in the UI until Blender restarts.
    # -----------------------------------------------------

    stale_ids = [
        implementation_id
        for implementation_id
        in _registered_implementation_ids
        if implementation_id
        not in current_ids
    ]

    for implementation_id in (
        stale_ids
    ):
        PIPELINE_REGISTRY.unregister(
            implementation_id
        )

    _registered_implementation_ids.clear()

    _registered_implementation_ids.extend(
        current_ids
    )

    return tuple(
        registered
    )


def unregister_builtin_implementations() -> None:
    """
    Remove only implementations registered by this package.

    Third-party/future implementations registered elsewhere
    are deliberately left untouched.
    """

    for implementation_id in reversed(
        _registered_implementation_ids
    ):
        PIPELINE_REGISTRY.unregister(
            implementation_id
        )

    _registered_implementation_ids.clear()


# ---------------------------------------------------------
# Blender module facade
# ---------------------------------------------------------

def register() -> None:
    """
    Blender add-on registration entry point.

    The root __init__.py will eventually register modules in:

        properties
            ↓
        implementations
            ↓
        operators
            ↓
        ui

    This guarantees implementation availability checks can
    inspect Blender settings if needed.
    """

    register_builtin_implementations(
        replace=True
    )


def unregister() -> None:
    unregister_builtin_implementations()


# ---------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------

def registered_builtin_ids() -> tuple[
    str,
    ...
]:
    """
    Return stable ids currently bootstrapped by Meshvenn.

    Useful for diagnostics and the future UI.
    """

    return tuple(
        _registered_implementation_ids
    )


def builtin_implementation_count() -> int:
    return len(
        _registered_implementation_ids
    )