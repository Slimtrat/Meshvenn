from __future__ import annotations

from collections.abc import (
    Callable,
)

from ..core.pipeline_contracts import (
    PipelineImplementation,
    PipelineStage,
)
from ..core.pipeline_registry import (
    PIPELINE_REGISTRY,
)


# ---------------------------------------------------------
# Built-in implementation imports
#
# core/
#     owns algorithms
#
# implementations/
#     adapts algorithms to PipelineImplementation
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
#
# Registration order controls UI ordering only.
#
# It MUST NOT control which implementation becomes the
# default for a stage.
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
# Explicit defaults
#
# This mapping is the single source of truth for registry
# defaults.
#
# Adding another implementation to a stage must therefore
# never accidentally change the default simply because its
# factory appears later in the catalog.
#
# Example:
#
#     MATERIAL
#
#       projected-color-v1.2  <- default
#       uv-bake-v2
#
# ---------------------------------------------------------

BUILTIN_DEFAULT_IMPLEMENTATION_IDS: dict[
    PipelineStage,
    str,
] = {
    PipelineStage.INPUT:
        "projection-images",

    PipelineStage.GEOMETRY:
        "native-visual-hull",

    PipelineStage.MATERIAL:
        "projected-color-v1.2",
}


# ---------------------------------------------------------
# Registration state
# ---------------------------------------------------------

_registered_implementation_ids: list[
    str
] = []


# ---------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------

def _instantiate_builtin_implementations(
) -> tuple[
    PipelineImplementation,
    ...
]:
    return tuple(
        factory()
        for factory
        in BUILTIN_IMPLEMENTATION_FACTORIES
    )


def _validate_builtin_catalog(
    implementations: tuple[
        PipelineImplementation,
        ...
    ],
) -> None:
    """
    Validate static catalog invariants before mutating the
    global registry.

    This prevents a partially-registered built-in catalog
    when its configuration is invalid.
    """

    ids: set[
        str
    ] = set()

    ids_by_stage: dict[
        PipelineStage,
        set[
            str
        ],
    ] = {
        stage: set()
        for stage
        in PipelineStage
    }

    for implementation in (
        implementations
    ):
        descriptor = (
            implementation
            .descriptor
        )

        implementation_id = (
            descriptor.identifier
        )

        if implementation_id in ids:
            raise RuntimeError(
                (
                    "Duplicate built-in implementation "
                    f'id: "{implementation_id}".'
                )
            )

        ids.add(
            implementation_id
        )

        ids_by_stage[
            descriptor.stage
        ].add(
            implementation_id
        )

    # -----------------------------------------------------
    # Every explicitly configured default must:
    #
    #   1. exist in the built-in catalog;
    #   2. belong to the configured stage.
    # -----------------------------------------------------

    for (
        stage,
        implementation_id,
    ) in (
        BUILTIN_DEFAULT_IMPLEMENTATION_IDS
        .items()
    ):
        if (
            implementation_id
            not in ids
        ):
            raise RuntimeError(
                (
                    "Built-in default implementation "
                    f'"{implementation_id}" for stage '
                    f'"{stage.value}" is not present '
                    "in the built-in catalog."
                )
            )

        if (
            implementation_id
            not in ids_by_stage[
                stage
            ]
        ):
            raise RuntimeError(
                (
                    "Built-in default implementation "
                    f'"{implementation_id}" does not '
                    "belong to pipeline stage "
                    f'"{stage.value}".'
                )
            )


# ---------------------------------------------------------
# Defaults
# ---------------------------------------------------------

def _apply_builtin_defaults() -> None:
    """
    Apply defaults only after every built-in implementation
    has been registered.

    PipelineRegistry currently promotes the first
    implementation registered for an empty stage to default.

    That behaviour remains useful for third-party registries,
    but Meshvenn's built-ins must not rely on registration
    order.

    Therefore this function explicitly overwrites the final
    default of every built-in stage.
    """

    for (
        stage,
        implementation_id,
    ) in (
        BUILTIN_DEFAULT_IMPLEMENTATION_IDS
        .items()
    ):
        PIPELINE_REGISTRY.set_default(
            stage,
            implementation_id,
        )


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

    Stable implementation ids therefore remain the source
    of truth.

    Current built-ins:

        INPUT
            projection-images

        GEOMETRY
            native-visual-hull

        MATERIAL
            projected-color-v1.2

    Future example:

        MATERIAL
            projected-color-v1.2
            uv-bake-v2

    Adding that second MATERIAL implementation must not
    change the existing default unless
    BUILTIN_DEFAULT_IMPLEMENTATION_IDS is modified
    explicitly.
    """

    implementations = (
        _instantiate_builtin_implementations()
    )

    _validate_builtin_catalog(
        implementations
    )

    registered: list[
        PipelineImplementation
    ] = []

    current_ids: list[
        str
    ] = []

    # -----------------------------------------------------
    # Register without relying on the `default` argument.
    #
    # PipelineRegistry may temporarily assign the first
    # implementation of a stage as its default.
    #
    # _apply_builtin_defaults() below establishes the final
    # authoritative state.
    # -----------------------------------------------------

    for implementation in (
        implementations
    ):
        descriptor = (
            implementation
            .descriptor
        )

        PIPELINE_REGISTRY.register(
            implementation,
            default=False,
            replace=replace,
        )

        registered.append(
            implementation
        )

        current_ids.append(
            descriptor.identifier
        )

    # -----------------------------------------------------
    # Remove built-ins remembered from a previous Blender
    # reload but no longer present in the catalog.
    #
    # Example:
    #
    #     uv-bake-v1
    #         ↓ reload after rename
    #     uv-bake-v2
    # -----------------------------------------------------

    stale_ids = [
        implementation_id
        for implementation_id
        in _registered_implementation_ids
        if (
            implementation_id
            not in current_ids
        )
    ]

    for implementation_id in (
        stale_ids
    ):
        PIPELINE_REGISTRY.unregister(
            implementation_id
        )

    # -----------------------------------------------------
    # Defaults are applied only after registration + stale
    # cleanup so their final state is deterministic.
    # -----------------------------------------------------

    _apply_builtin_defaults()

    _registered_implementation_ids.clear()

    _registered_implementation_ids.extend(
        current_ids
    )

    return tuple(
        registered
    )


def unregister_builtin_implementations(
) -> None:
    """
    Remove only implementations owned by Meshvenn.

    External implementations registered by another package
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
    Root registration order:

        properties
            ↓
        implementations
            ↓
        operators
            ↓
        ui
    """

    register_builtin_implementations(
        replace=True
    )


def unregister() -> None:
    unregister_builtin_implementations()


# ---------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------

def registered_builtin_ids(
) -> tuple[
    str,
    ...
]:
    return tuple(
        _registered_implementation_ids
    )


def builtin_implementation_count(
) -> int:
    return len(
        _registered_implementation_ids
    )


def builtin_default_id(
    stage: PipelineStage,
) -> str | None:
    """
    Return Meshvenn's configured default independently from
    the current runtime registry state.
    """

    return (
        BUILTIN_DEFAULT_IMPLEMENTATION_IDS
        .get(
            PipelineStage(
                stage
            )
        )
    )