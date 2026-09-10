from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Iterable,
    Iterator,
)

from .pipeline_contracts import (
    ImplementationAvailability,
    ImplementationDescriptor,
    PipelineContext,
    PipelineImplementation,
    PipelinePlan,
    PipelineStage,
    PipelineStageSelection,
    PIPELINE_STAGE_ORDER,
    validate_implementation_id,
)


# ---------------------------------------------------------
# Errors
# ---------------------------------------------------------

class PipelineRegistryError(
    RuntimeError
):
    """
    Base error raised by the pipeline registry.
    """


class DuplicateImplementationError(
    PipelineRegistryError
):
    """
    Raised when an implementation id is already registered.
    """


class UnknownImplementationError(
    PipelineRegistryError
):
    """
    Raised when an implementation cannot be resolved.
    """


class StageMismatchError(
    PipelineRegistryError
):
    """
    Raised when an implementation is requested for the wrong
    pipeline stage.
    """


class InvalidImplementationError(
    PipelineRegistryError
):
    """
    Raised when an object does not satisfy the implementation
    contract.
    """


# ---------------------------------------------------------
# Registry entry
# ---------------------------------------------------------

@dataclass(frozen=True)
class PipelineRegistryEntry:
    """
    Immutable registry entry.

    Registration order is preserved by PipelineRegistry so
    the Blender UI can present implementations predictably.
    """

    implementation: PipelineImplementation

    descriptor: ImplementationDescriptor

    registration_index: int

    is_default: bool = False


# ---------------------------------------------------------
# Availability entry
# ---------------------------------------------------------

@dataclass(frozen=True)
class PipelineAvailabilityEntry:
    """
    Runtime availability snapshot for one implementation.
    """

    descriptor: ImplementationDescriptor

    availability: ImplementationAvailability

    is_default: bool = False

    @property
    def identifier(
        self,
    ) -> str:
        return (
            self.descriptor
            .identifier
        )

    @property
    def stage(
        self,
    ) -> PipelineStage:
        return (
            self.descriptor
            .stage
        )

    @property
    def available(
        self,
    ) -> bool:
        return (
            self.availability
            .available
        )


# ---------------------------------------------------------
# Plan validation
# ---------------------------------------------------------

@dataclass(frozen=True)
class PipelinePlanValidationIssue:
    """
    One problem found while validating a PipelinePlan.
    """

    stage: PipelineStage

    implementation_id: str

    message: str


@dataclass(frozen=True)
class PipelinePlanValidationResult:
    """
    Complete validation result for one pipeline plan.
    """

    issues: tuple[
        PipelinePlanValidationIssue,
        ...
    ]

    @property
    def valid(
        self,
    ) -> bool:
        return not self.issues

    def raise_for_errors(
        self,
    ) -> None:
        if self.valid:
            return

        messages = [
            (
                f"{issue.stage.value}: "
                f"{issue.implementation_id}: "
                f"{issue.message}"
            )
            for issue
            in self.issues
        ]

        raise PipelineRegistryError(
            (
                "Pipeline plan is invalid:\n"
                + "\n".join(
                    f"- {message}"
                    for message
                    in messages
                )
            )
        )


# ---------------------------------------------------------
# Implementation contract validation
# ---------------------------------------------------------

def _read_descriptor(
    implementation: PipelineImplementation,
) -> ImplementationDescriptor:
    """
    Read and validate an implementation descriptor.

    We validate structurally instead of relying exclusively
    on isinstance(..., PipelineImplementation), because the
    public contract is intentionally lightweight and should
    remain friendly to pure Python implementations, Blender
    implementations and test doubles.
    """

    if implementation is None:
        raise InvalidImplementationError(
            "Pipeline implementation cannot be None."
        )

    if not hasattr(
        implementation,
        "descriptor",
    ):
        raise InvalidImplementationError(
            (
                "Pipeline implementation must expose "
                "a descriptor property."
            )
        )

    descriptor = getattr(
        implementation,
        "descriptor",
    )

    if not isinstance(
        descriptor,
        ImplementationDescriptor,
    ):
        raise InvalidImplementationError(
            (
                "Pipeline implementation descriptor "
                "must be an ImplementationDescriptor."
            )
        )

    if not callable(
        getattr(
            implementation,
            "availability",
            None,
        )
    ):
        raise InvalidImplementationError(
            (
                f'Implementation "{descriptor.identifier}" '
                "must define availability(context)."
            )
        )

    if not callable(
        getattr(
            implementation,
            "execute",
            None,
        )
    ):
        raise InvalidImplementationError(
            (
                f'Implementation "{descriptor.identifier}" '
                "must define execute(context)."
            )
        )

    return descriptor


# ---------------------------------------------------------
# Registry
# ---------------------------------------------------------

class PipelineRegistry:
    """
    Registry of all available Meshvenn pipeline
    implementations.

    The registry is deliberately independent from Blender.

    It provides four main responsibilities:

        1. register concrete implementations;
        2. list implementations by pipeline stage;
        3. resolve stable implementation ids;
        4. expose runtime availability to the UI.

    Example:

        registry.register(
            NativeVisualHullImplementation(),
            default=True,
        )

        registry.register(
            ProjectedColorImplementation(),
            default=True,
        )

        material_choices = (
            registry.descriptors(
                PipelineStage.MATERIAL
            )
        )

    The UI never needs to import either concrete class.
    """

    def __init__(
        self,
    ) -> None:
        self._entries: dict[
            str,
            PipelineRegistryEntry,
        ] = {}

        self._stage_ids: dict[
            PipelineStage,
            list[
                str
            ],
        ] = {
            stage: []
            for stage
            in PIPELINE_STAGE_ORDER
        }

        self._default_ids: dict[
            PipelineStage,
            str,
        ] = {}

        self._registration_counter = 0

    # -----------------------------------------------------
    # General state
    # -----------------------------------------------------

    def __len__(
        self,
    ) -> int:
        return len(
            self._entries
        )

    def __bool__(
        self,
    ) -> bool:
        return bool(
            self._entries
        )

    def __contains__(
        self,
        implementation_id: object,
    ) -> bool:
        if not isinstance(
            implementation_id,
            str,
        ):
            return False

        return (
            implementation_id
            in self._entries
        )

    def __iter__(
        self,
    ) -> Iterator[
        PipelineImplementation
    ]:
        for entry in (
            self.entries()
        ):
            yield (
                entry
                .implementation
            )

    def clear(
        self,
    ) -> None:
        self._entries.clear()

        for ids in (
            self._stage_ids
            .values()
        ):
            ids.clear()

        self._default_ids.clear()

        self._registration_counter = 0

    # -----------------------------------------------------
    # Registration
    # -----------------------------------------------------

    def register(
        self,
        implementation: PipelineImplementation,
        *,
        default: bool = False,
        replace: bool = False,
    ) -> PipelineImplementation:
        """
        Register one implementation.

        Implementation identifiers are globally unique.

        `replace=True` is useful during Blender add-on reloads
        because module reloads can create a new Python object
        for the same stable implementation id.

        Replacing an implementation never silently changes
        its pipeline stage.
        """

        descriptor = (
            _read_descriptor(
                implementation
            )
        )

        implementation_id = (
            descriptor.identifier
        )

        existing = (
            self._entries.get(
                implementation_id
            )
        )

        if existing is not None:
            if not replace:
                raise (
                    DuplicateImplementationError(
                        (
                            "Pipeline implementation "
                            f'"{implementation_id}" '
                            "is already registered."
                        )
                    )
                )

            if (
                existing
                .descriptor
                .stage
                != descriptor.stage
            ):
                raise StageMismatchError(
                    (
                        "Cannot replace implementation "
                        f'"{implementation_id}" from stage '
                        f'"{existing.descriptor.stage.value}" '
                        "with implementation from stage "
                        f'"{descriptor.stage.value}".'
                    )
                )

            replacement = (
                PipelineRegistryEntry(
                    implementation=(
                        implementation
                    ),
                    descriptor=(
                        descriptor
                    ),
                    registration_index=(
                        existing
                        .registration_index
                    ),
                    is_default=(
                        existing.is_default
                        or default
                    ),
                )
            )

            self._entries[
                implementation_id
            ] = replacement

            if (
                replacement
                .is_default
            ):
                self.set_default(
                    descriptor.stage,
                    implementation_id,
                )

            return implementation

        entry = (
            PipelineRegistryEntry(
                implementation=(
                    implementation
                ),
                descriptor=(
                    descriptor
                ),
                registration_index=(
                    self
                    ._registration_counter
                ),
                is_default=False,
            )
        )

        self._registration_counter += 1

        self._entries[
            implementation_id
        ] = entry

        self._stage_ids[
            descriptor.stage
        ].append(
            implementation_id
        )

        # -------------------------------------------------
        # First implementation automatically becomes the
        # default unless another one already exists.
        #
        # This allows a stage to work without requiring
        # additional bootstrap configuration.
        # -------------------------------------------------

        if (
            descriptor.stage
            not in self._default_ids
        ):
            default = True

        if default:
            self.set_default(
                descriptor.stage,
                implementation_id,
            )

        return implementation

    def unregister(
        self,
        implementation_id: str,
    ) -> (
        PipelineImplementation
        | None
    ):
        """
        Remove one implementation.

        If the removed implementation was the stage default,
        the first remaining implementation becomes default.
        """

        normalized_id = (
            validate_implementation_id(
                implementation_id
            )
        )

        entry = (
            self._entries.pop(
                normalized_id,
                None,
            )
        )

        if entry is None:
            return None

        stage = (
            entry.descriptor.stage
        )

        stage_ids = (
            self._stage_ids[
                stage
            ]
        )

        try:
            stage_ids.remove(
                normalized_id
            )

        except ValueError:
            pass

        if (
            self._default_ids.get(
                stage
            )
            == normalized_id
        ):
            self._default_ids.pop(
                stage,
                None,
            )

            if stage_ids:
                self.set_default(
                    stage,
                    stage_ids[0],
                )

        return (
            entry
            .implementation
        )

    # -----------------------------------------------------
    # Defaults
    # -----------------------------------------------------

    def set_default(
        self,
        stage: PipelineStage,
        implementation_id: str,
    ) -> None:
        normalized_stage = (
            PipelineStage(
                stage
            )
        )

        normalized_id = (
            validate_implementation_id(
                implementation_id
            )
        )

        entry = self.require_entry(
            normalized_id
        )

        if (
            entry.descriptor.stage
            != normalized_stage
        ):
            raise StageMismatchError(
                (
                    f'Implementation "{normalized_id}" '
                    "belongs to stage "
                    f'"{entry.descriptor.stage.value}", '
                    "not "
                    f'"{normalized_stage.value}".'
                )
            )

        previous_id = (
            self._default_ids.get(
                normalized_stage
            )
        )

        if (
            previous_id is not None
            and previous_id
            in self._entries
        ):
            previous = (
                self._entries[
                    previous_id
                ]
            )

            self._entries[
                previous_id
            ] = PipelineRegistryEntry(
                implementation=(
                    previous
                    .implementation
                ),
                descriptor=(
                    previous
                    .descriptor
                ),
                registration_index=(
                    previous
                    .registration_index
                ),
                is_default=False,
            )

        current = (
            self._entries[
                normalized_id
            ]
        )

        self._entries[
            normalized_id
        ] = PipelineRegistryEntry(
            implementation=(
                current
                .implementation
            ),
            descriptor=(
                current
                .descriptor
            ),
            registration_index=(
                current
                .registration_index
            ),
            is_default=True,
        )

        self._default_ids[
            normalized_stage
        ] = normalized_id

    def default_id(
        self,
        stage: PipelineStage,
    ) -> str | None:
        normalized_stage = (
            PipelineStage(
                stage
            )
        )

        return self._default_ids.get(
            normalized_stage
        )

    def default_entry(
        self,
        stage: PipelineStage,
    ) -> (
        PipelineRegistryEntry
        | None
    ):
        implementation_id = (
            self.default_id(
                stage
            )
        )

        if implementation_id is None:
            return None

        return self._entries.get(
            implementation_id
        )

    def default(
        self,
        stage: PipelineStage,
    ) -> (
        PipelineImplementation
        | None
    ):
        entry = (
            self.default_entry(
                stage
            )
        )

        if entry is None:
            return None

        return (
            entry
            .implementation
        )

    # -----------------------------------------------------
    # Lookup
    # -----------------------------------------------------

    def get_entry(
        self,
        implementation_id: str,
    ) -> (
        PipelineRegistryEntry
        | None
    ):
        normalized_id = (
            validate_implementation_id(
                implementation_id
            )
        )

        return self._entries.get(
            normalized_id
        )

    def require_entry(
        self,
        implementation_id: str,
    ) -> PipelineRegistryEntry:
        entry = self.get_entry(
            implementation_id
        )

        if entry is None:
            raise UnknownImplementationError(
                (
                    "Unknown pipeline implementation: "
                    f'"{implementation_id}".'
                )
            )

        return entry

    def get(
        self,
        implementation_id: str,
    ) -> (
        PipelineImplementation
        | None
    ):
        entry = self.get_entry(
            implementation_id
        )

        if entry is None:
            return None

        return (
            entry
            .implementation
        )

    def require(
        self,
        implementation_id: str,
        *,
        stage: (
            PipelineStage
            | None
        ) = None,
    ) -> PipelineImplementation:
        entry = self.require_entry(
            implementation_id
        )

        if stage is not None:
            expected_stage = (
                PipelineStage(
                    stage
                )
            )

            if (
                entry.descriptor.stage
                != expected_stage
            ):
                raise StageMismatchError(
                    (
                        f'Implementation "{implementation_id}" '
                        "belongs to "
                        f'"{entry.descriptor.stage.value}", '
                        "but "
                        f'"{expected_stage.value}" '
                        "was requested."
                    )
                )

        return (
            entry
            .implementation
        )

    # -----------------------------------------------------
    # Listing
    # -----------------------------------------------------

    def entries(
        self,
        stage: (
            PipelineStage
            | None
        ) = None,
    ) -> tuple[
        PipelineRegistryEntry,
        ...
    ]:
        if stage is None:
            return tuple(
                sorted(
                    self._entries.values(),
                    key=lambda item: (
                        PIPELINE_STAGE_ORDER.index(
                            item
                            .descriptor
                            .stage
                        ),
                        item
                        .registration_index,
                    ),
                )
            )

        normalized_stage = (
            PipelineStage(
                stage
            )
        )

        return tuple(
            self._entries[
                implementation_id
            ]
            for implementation_id
            in self._stage_ids[
                normalized_stage
            ]
            if implementation_id
            in self._entries
        )

    def implementations(
        self,
        stage: (
            PipelineStage
            | None
        ) = None,
    ) -> tuple[
        PipelineImplementation,
        ...
    ]:
        return tuple(
            entry.implementation
            for entry
            in self.entries(
                stage
            )
        )

    def descriptors(
        self,
        stage: (
            PipelineStage
            | None
        ) = None,
    ) -> tuple[
        ImplementationDescriptor,
        ...
    ]:
        return tuple(
            entry.descriptor
            for entry
            in self.entries(
                stage
            )
        )

    def implementation_ids(
        self,
        stage: (
            PipelineStage
            | None
        ) = None,
    ) -> tuple[
        str,
        ...
    ]:
        return tuple(
            descriptor.identifier
            for descriptor
            in self.descriptors(
                stage
            )
        )

    def has_stage(
        self,
        stage: PipelineStage,
    ) -> bool:
        normalized_stage = (
            PipelineStage(
                stage
            )
        )

        return bool(
            self._stage_ids[
                normalized_stage
            ]
        )

    # -----------------------------------------------------
    # Availability
    # -----------------------------------------------------

    def availability(
        self,
        implementation_id: str,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        implementation = self.require(
            implementation_id
        )

        result = implementation.availability(
            context
        )

        if not isinstance(
            result,
            ImplementationAvailability,
        ):
            raise InvalidImplementationError(
                (
                    f'Implementation "{implementation_id}" '
                    "availability() must return "
                    "ImplementationAvailability."
                )
            )

        return result

    def availability_entries(
        self,
        stage: PipelineStage,
        context: PipelineContext,
    ) -> tuple[
        PipelineAvailabilityEntry,
        ...
    ]:
        normalized_stage = (
            PipelineStage(
                stage
            )
        )

        result: list[
            PipelineAvailabilityEntry
        ] = []

        for entry in self.entries(
            normalized_stage
        ):
            availability = (
                entry
                .implementation
                .availability(
                    context
                )
            )

            if not isinstance(
                availability,
                ImplementationAvailability,
            ):
                raise InvalidImplementationError(
                    (
                        "Implementation "
                        f'"{entry.descriptor.identifier}" '
                        "availability() must return "
                        "ImplementationAvailability."
                    )
                )

            result.append(
                PipelineAvailabilityEntry(
                    descriptor=(
                        entry.descriptor
                    ),
                    availability=(
                        availability
                    ),
                    is_default=(
                        entry.is_default
                    ),
                )
            )

        return tuple(
            result
        )

    def available_entries(
        self,
        stage: PipelineStage,
        context: PipelineContext,
    ) -> tuple[
        PipelineAvailabilityEntry,
        ...
    ]:
        return tuple(
            entry
            for entry
            in self.availability_entries(
                stage,
                context,
            )
            if entry.available
        )

    # -----------------------------------------------------
    # Selection resolution
    # -----------------------------------------------------

    def resolve_selection(
        self,
        selection: PipelineStageSelection,
    ) -> PipelineImplementation:
        """
        Resolve and verify one PipelineStageSelection.
        """

        return self.require(
            selection.implementation_id,
            stage=(
                selection.stage
            ),
        )

    def resolve_stage(
        self,
        stage: PipelineStage,
        implementation_id: (
            str
            | None
        ) = None,
    ) -> PipelineImplementation:
        """
        Resolve a specific implementation or the default
        implementation for a stage.
        """

        normalized_stage = (
            PipelineStage(
                stage
            )
        )

        if implementation_id:
            return self.require(
                implementation_id,
                stage=(
                    normalized_stage
                ),
            )

        implementation = self.default(
            normalized_stage
        )

        if implementation is None:
            raise UnknownImplementationError(
                (
                    "No implementation registered "
                    "for pipeline stage "
                    f'"{normalized_stage.value}".'
                )
            )

        return implementation

    # -----------------------------------------------------
    # Plan validation
    # -----------------------------------------------------

    def validate_plan(
        self,
        plan: PipelinePlan,
        context: (
            PipelineContext
            | None
        ) = None,
        *,
        check_availability: bool = True,
    ) -> PipelinePlanValidationResult:
        """
        Validate that every enabled PipelinePlan selection:

            - exists;
            - belongs to the correct stage;
            - is available in the current context.

        Dependency/output validation is intentionally not
        performed here. That belongs to the orchestrator at
        execution time because outputs are created stage by
        stage.
        """

        if context is None:
            context = (
                PipelineContext()
            )

        issues: list[
            PipelinePlanValidationIssue
        ] = []

        for selection in (
            plan.enabled_selections
        ):
            entry = (
                self._entries.get(
                    selection
                    .implementation_id
                )
            )

            if entry is None:
                issues.append(
                    PipelinePlanValidationIssue(
                        stage=(
                            selection.stage
                        ),
                        implementation_id=(
                            selection
                            .implementation_id
                        ),
                        message=(
                            "Implementation is not registered."
                        ),
                    )
                )

                continue

            if (
                entry
                .descriptor
                .stage
                != selection.stage
            ):
                issues.append(
                    PipelinePlanValidationIssue(
                        stage=(
                            selection.stage
                        ),
                        implementation_id=(
                            selection
                            .implementation_id
                        ),
                        message=(
                            "Implementation belongs to "
                            f'"{entry.descriptor.stage.value}" '
                            "instead of "
                            f'"{selection.stage.value}".'
                        ),
                    )
                )

                continue

            if not check_availability:
                continue

            try:
                availability = (
                    entry
                    .implementation
                    .availability(
                        context
                    )
                )

            except Exception as exc:
                issues.append(
                    PipelinePlanValidationIssue(
                        stage=(
                            selection.stage
                        ),
                        implementation_id=(
                            selection
                            .implementation_id
                        ),
                        message=(
                            "Availability check failed: "
                            f"{exc}"
                        ),
                    )
                )

                continue

            if not isinstance(
                availability,
                ImplementationAvailability,
            ):
                issues.append(
                    PipelinePlanValidationIssue(
                        stage=(
                            selection.stage
                        ),
                        implementation_id=(
                            selection
                            .implementation_id
                        ),
                        message=(
                            "availability() returned an "
                            "invalid result."
                        ),
                    )
                )

                continue

            if not availability.available:
                reason = (
                    availability.reason.strip()
                    or "Implementation is unavailable."
                )

                issues.append(
                    PipelinePlanValidationIssue(
                        stage=(
                            selection.stage
                        ),
                        implementation_id=(
                            selection
                            .implementation_id
                        ),
                        message=(
                            reason
                        ),
                    )
                )

        return (
            PipelinePlanValidationResult(
                issues=tuple(
                    issues
                )
            )
        )


# ---------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------

def build_default_plan(
    registry: PipelineRegistry,
    *,
    include_optional: bool = True,
) -> PipelinePlan:
    """
    Build a PipelinePlan from the current registry defaults.

    This will later be useful for:

        - first-run Blender settings;
        - headless generation;
        - reset-to-default;
        - migration from the old single-engine UI.
    """

    selections: list[
        PipelineStageSelection
    ] = []

    optional_stages = {
        PipelineStage.MATERIAL,
        PipelineStage.RIG,
        PipelineStage.EXPORT,
    }

    for stage in (
        PIPELINE_STAGE_ORDER
    ):
        if (
            not include_optional
            and stage
            in optional_stages
        ):
            continue

        implementation_id = (
            registry.default_id(
                stage
            )
        )

        if implementation_id is None:
            continue

        selections.append(
            PipelineStageSelection(
                stage=stage,
                implementation_id=(
                    implementation_id
                ),
                enabled=True,
            )
        )

    return PipelinePlan(
        selections=tuple(
            selections
        )
    )


def register_many(
    registry: PipelineRegistry,
    implementations: Iterable[
        PipelineImplementation
    ],
    *,
    replace: bool = False,
) -> None:
    """
    Register a collection of implementations.

    The first implementation for each stage automatically
    becomes that stage's default.
    """

    for implementation in (
        implementations
    ):
        registry.register(
            implementation,
            replace=replace,
        )


# ---------------------------------------------------------
# Global application registry
# ---------------------------------------------------------

PIPELINE_REGISTRY = (
    PipelineRegistry()
)


# ---------------------------------------------------------
# Module-level facade
#
# Most Blender-side code should use these helpers instead of
# carrying the registry instance around explicitly.
# ---------------------------------------------------------

def register_implementation(
    implementation: PipelineImplementation,
    *,
    default: bool = False,
    replace: bool = False,
) -> PipelineImplementation:
    return PIPELINE_REGISTRY.register(
        implementation,
        default=default,
        replace=replace,
    )


def unregister_implementation(
    implementation_id: str,
) -> (
    PipelineImplementation
    | None
):
    return PIPELINE_REGISTRY.unregister(
        implementation_id
    )


def get_implementation(
    implementation_id: str,
) -> (
    PipelineImplementation
    | None
):
    return PIPELINE_REGISTRY.get(
        implementation_id
    )


def require_implementation(
    implementation_id: str,
    *,
    stage: (
        PipelineStage
        | None
    ) = None,
) -> PipelineImplementation:
    return PIPELINE_REGISTRY.require(
        implementation_id,
        stage=stage,
    )


def implementations_for_stage(
    stage: PipelineStage,
) -> tuple[
    PipelineImplementation,
    ...
]:
    return (
        PIPELINE_REGISTRY
        .implementations(
            stage
        )
    )


def descriptors_for_stage(
    stage: PipelineStage,
) -> tuple[
    ImplementationDescriptor,
    ...
]:
    return (
        PIPELINE_REGISTRY
        .descriptors(
            stage
        )
    )


def availability_for_stage(
    stage: PipelineStage,
    context: PipelineContext,
) -> tuple[
    PipelineAvailabilityEntry,
    ...
]:
    return (
        PIPELINE_REGISTRY
        .availability_entries(
            stage,
            context,
        )
    )


def default_implementation_id(
    stage: PipelineStage,
) -> str | None:
    return (
        PIPELINE_REGISTRY
        .default_id(
            stage
        )
    )


def clear_registry() -> None:
    """
    Primarily useful during Blender unregister/reload and in
    tests.
    """

    PIPELINE_REGISTRY.clear()