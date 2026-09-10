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


# =========================================================
# Built-in implementations
#
# core/
#     owns algorithms
#
# implementations/
#     adapts algorithms to PipelineImplementation
# =========================================================

from .projection_images import (
    ProjectionImagesImplementation,
)

from .native_visual_hull import (
    NativeVisualHullImplementation,
)

from .sdf_reconstruction import (
    SDFReconstructionImplementation,
)

from .projected_color import (
    ProjectedColorImplementation,
)

from .uv_bake import (
    UVBakeImplementation,
)


# =========================================================
# Types
# =========================================================

ImplementationFactory = Callable[
    [],
    PipelineImplementation,
]


# =========================================================
# Built-in catalog
#
# Registration order controls UI ordering only.
#
# It MUST NOT control which implementation becomes the
# default for a stage.
# =========================================================

BUILTIN_IMPLEMENTATION_FACTORIES: tuple[
    ImplementationFactory,
    ...
] = (
    # -----------------------------------------------------
    # INPUT
    # -----------------------------------------------------

    ProjectionImagesImplementation,

    # -----------------------------------------------------
    # GEOMETRY
    #
    # Native Visual Hull remains first for UI continuity,
    # but default selection is explicit below.
    # -----------------------------------------------------

    NativeVisualHullImplementation,
    SDFReconstructionImplementation,

    # -----------------------------------------------------
    # MATERIAL
    # -----------------------------------------------------

    ProjectedColorImplementation,
    UVBakeImplementation,
)


# =========================================================
# Explicit defaults
#
# One authoritative default per built-in stage.
#
# Current choices:
#
#     INPUT
#         Projection Images
#
#     GEOMETRY
#         Native Visual Hull       <- default
#         SDF Reconstruction V1
#
#     MATERIAL
#         Projected Color V1.2     <- default
#         UV Bake V2
#
# Experimental additions MUST NOT silently replace these
# defaults.
# =========================================================

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


# =========================================================
# Registration state
# =========================================================

_registered_implementation_ids: list[
    str
] = []


# =========================================================
# Catalog construction
# =========================================================

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
    Validate the complete catalog before mutating the global
    registry.

    This protects Blender reloads from ending up with a
    partially-registered implementation catalog.
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
                    "Duplicate built-in pipeline "
                    "implementation id: "
                    f'"{implementation_id}".'
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
    # Validate explicit defaults.
    #
    # A configured default must:
    #
    #     exist
    #     belong to the expected stage
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
                    f'"{stage.value}" does not exist '
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
                    f'"{implementation_id}" belongs to '
                    "the wrong pipeline stage. "
                    f'Expected "{stage.value}".'
                )
            )


# =========================================================
# Explicit defaults
# =========================================================

def _apply_builtin_defaults(
) -> None:
    """
    Force Meshvenn's authoritative defaults after all
    implementations have been registered.

    PipelineRegistry automatically promotes the first
    implementation of an empty stage. That remains useful
    for generic/third-party registries.

    Meshvenn's own defaults are nevertheless explicit so
    adding an experimental implementation cannot silently
    alter product behaviour.
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


# =========================================================
# Registration
# =========================================================

def register_builtin_implementations(
    *,
    replace: bool = True,
) -> tuple[
    PipelineImplementation,
    ...
]:
    """
    Register every built-in Meshvenn implementation.

    Current catalog:

        INPUT

            projection-images
                <- default

        GEOMETRY

            native-visual-hull
                <- default

            sdf-reconstruction-v1
                experimental
                Python reference backend

        MATERIAL

            projected-color-v1.2
                <- default

            uv-bake-v2
                experimental

        RIG

            none yet

        EXPORT

            none yet

    `replace=True` is intentional during Blender add-on
    reloads.

    Stable implementation ids remain the source of truth.
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
    # Register all implementations first.
    #
    # Do not rely on registration order for final defaults.
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
    # Remove stale built-ins left by an earlier Blender
    # reload.
    #
    # Example:
    #
    #     implementation-v1
    #         ↓ code reload
    #     implementation-v2
    #
    # Without this cleanup the old implementation could
    # remain selectable until Blender restarts.
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
    # Establish final deterministic defaults.
    #
    # Important:
    #
    # registering sdf-reconstruction-v1 MUST NOT replace:
    #
    #     GEOMETRY -> native-visual-hull
    # -----------------------------------------------------

    _apply_builtin_defaults()

    # -----------------------------------------------------
    # Commit registration state only after the complete
    # catalog has succeeded.
    # -----------------------------------------------------

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

    Third-party implementations registered independently
    remain untouched.
    """

    for implementation_id in reversed(
        _registered_implementation_ids
    ):
        PIPELINE_REGISTRY.unregister(
            implementation_id
        )

    _registered_implementation_ids.clear()


# =========================================================
# Blender module lifecycle
# =========================================================

def register(
) -> None:
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


def unregister(
) -> None:
    unregister_builtin_implementations()


# =========================================================
# Diagnostics
# =========================================================

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
    current registry runtime state.
    """

    return (
        BUILTIN_DEFAULT_IMPLEMENTATION_IDS
        .get(
            PipelineStage(
                stage
            )
        )
    )