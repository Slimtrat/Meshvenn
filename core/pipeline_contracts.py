from __future__ import annotations

import re

from dataclasses import (
    dataclass,
    field,
)
from enum import Enum
from typing import (
    Any,
    Mapping,
    Protocol,
    runtime_checkable,
)


# ---------------------------------------------------------
# Identifiers
# ---------------------------------------------------------

IMPLEMENTATION_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]*$"
)


def validate_implementation_id(
    value: str,
) -> str:
    """
    Validate a stable implementation identifier.

    Examples:

        native-visual-hull
        surface-nets
        projected-color-v1.2
        auto-rig.stytch

    These identifiers are intended to be persisted inside
    Blender settings and manifests, so they must remain
    stable and machine-friendly.
    """

    normalized = str(
        value
    ).strip()

    if not normalized:
        raise ValueError(
            "Implementation id cannot be empty."
        )

    if not IMPLEMENTATION_ID_PATTERN.fullmatch(
        normalized
    ):
        raise ValueError(
            (
                "Implementation id must contain only "
                "lowercase letters, digits, '.', '_' or '-'."
            )
        )

    return normalized


# ---------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------

class PipelineStage(
    str,
    Enum,
):
    """
    Stable high-level Meshvenn pipeline stages.

    The UI, registry and implementations all use these
    identifiers rather than depending directly on specific
    reconstruction/material/rig algorithms.
    """

    INPUT = "input"

    GEOMETRY = "geometry"

    MATERIAL = "material"

    RIG = "rig"

    EXPORT = "export"


@dataclass(frozen=True)
class PipelineStageSpec:
    """
    User-facing definition of one pipeline stage.

    This stays Blender-independent. Blender icons and layout
    remain the responsibility of ui.py.
    """

    stage: PipelineStage

    label: str

    description: str

    required_stages: tuple[
        PipelineStage,
        ...
    ] = ()

    optional: bool = False


PIPELINE_STAGE_SPECS: tuple[
    PipelineStageSpec,
    ...
] = (
    PipelineStageSpec(
        stage=PipelineStage.INPUT,
        label="Input",
        description=(
            "Images, projection views and source data."
        ),
        required_stages=(),
        optional=False,
    ),

    PipelineStageSpec(
        stage=PipelineStage.GEOMETRY,
        label="Geometry",
        description=(
            "Reconstruct the 3D surface from the source data."
        ),
        required_stages=(
            PipelineStage.INPUT,
        ),
        optional=False,
    ),

    PipelineStageSpec(
        stage=PipelineStage.MATERIAL,
        label="Material",
        description=(
            "Generate appearance information for the mesh."
        ),
        required_stages=(
            PipelineStage.GEOMETRY,
        ),
        optional=True,
    ),

    PipelineStageSpec(
        stage=PipelineStage.RIG,
        label="Rig",
        description=(
            "Generate or attach a skeleton and skinning data."
        ),
        required_stages=(
            PipelineStage.GEOMETRY,
        ),
        optional=True,
    ),

    PipelineStageSpec(
        stage=PipelineStage.EXPORT,
        label="Export",
        description=(
            "Prepare and export the generated asset."
        ),
        required_stages=(
            PipelineStage.GEOMETRY,
        ),
        optional=True,
    ),
)


PIPELINE_STAGE_ORDER: tuple[
    PipelineStage,
    ...
] = tuple(
    spec.stage
    for spec
    in PIPELINE_STAGE_SPECS
)


PIPELINE_STAGE_SPEC_BY_STAGE: dict[
    PipelineStage,
    PipelineStageSpec,
] = {
    spec.stage: spec
    for spec
    in PIPELINE_STAGE_SPECS
}


def stage_spec(
    stage: PipelineStage,
) -> PipelineStageSpec:
    try:
        return (
            PIPELINE_STAGE_SPEC_BY_STAGE[
                PipelineStage(stage)
            ]
        )

    except (
        KeyError,
        ValueError,
    ) as exc:
        raise ValueError(
            f"Unknown pipeline stage: {stage}"
        ) from exc


# ---------------------------------------------------------
# Implementation metadata
# ---------------------------------------------------------

@dataclass(frozen=True)
class ImplementationDescriptor:
    """
    Static metadata exposed by a pipeline implementation.

    The Blender UI can display implementations entirely from
    this structure without importing implementation details.
    """

    identifier: str

    stage: PipelineStage

    label: str

    description: str

    version: str = "1"

    experimental: bool = False

    supports_headless: bool = True

    capabilities: tuple[
        str,
        ...
    ] = ()

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "identifier",
            validate_implementation_id(
                self.identifier
            ),
        )

        object.__setattr__(
            self,
            "stage",
            PipelineStage(
                self.stage
            ),
        )

        label = str(
            self.label
        ).strip()

        if not label:
            raise ValueError(
                "Implementation label cannot be empty."
            )

        object.__setattr__(
            self,
            "label",
            label,
        )

        object.__setattr__(
            self,
            "description",
            str(
                self.description
            ).strip(),
        )

        version = str(
            self.version
        ).strip()

        if not version:
            raise ValueError(
                "Implementation version cannot be empty."
            )

        object.__setattr__(
            self,
            "version",
            version,
        )

        normalized_capabilities: list[
            str
        ] = []

        seen: set[
            str
        ] = set()

        for capability in (
            self.capabilities
        ):
            normalized = str(
                capability
            ).strip()

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(
                normalized
            )

            normalized_capabilities.append(
                normalized
            )

        object.__setattr__(
            self,
            "capabilities",
            tuple(
                normalized_capabilities
            ),
        )


# ---------------------------------------------------------
# Availability
# ---------------------------------------------------------

class AvailabilityState(
    str,
    Enum,
):
    READY = "ready"

    DEGRADED = "degraded"

    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ImplementationAvailability:
    """
    Runtime availability of one implementation.

    Example:

        Native C++
            READY

        Auto Rig
            UNAVAILABLE
            "Not implemented yet"

        CUDA engine
            UNAVAILABLE
            "CUDA runtime not found"
    """

    state: AvailabilityState

    reason: str = ""

    details: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    @property
    def available(
        self,
    ) -> bool:
        return self.state in {
            AvailabilityState.READY,
            AvailabilityState.DEGRADED,
        }

    @property
    def ready(
        self,
    ) -> bool:
        return (
            self.state
            == AvailabilityState.READY
        )

    @classmethod
    def ready_state(
        cls,
        *,
        details: Mapping[
            str,
            Any,
        ]
        | None = None,
    ) -> "ImplementationAvailability":
        return cls(
            state=(
                AvailabilityState.READY
            ),
            reason="",
            details=(
                details
                or {}
            ),
        )

    @classmethod
    def degraded(
        cls,
        reason: str,
        *,
        details: Mapping[
            str,
            Any,
        ]
        | None = None,
    ) -> "ImplementationAvailability":
        return cls(
            state=(
                AvailabilityState.DEGRADED
            ),
            reason=str(
                reason
            ),
            details=(
                details
                or {}
            ),
        )

    @classmethod
    def unavailable(
        cls,
        reason: str,
        *,
        details: Mapping[
            str,
            Any,
        ]
        | None = None,
    ) -> "ImplementationAvailability":
        return cls(
            state=(
                AvailabilityState.UNAVAILABLE
            ),
            reason=str(
                reason
            ),
            details=(
                details
                or {}
            ),
        )


# ---------------------------------------------------------
# Runtime context
# ---------------------------------------------------------

@dataclass
class PipelineContext:
    """
    Shared mutable context for one pipeline execution.

    This deliberately contains no hard dependency on bpy.

    Blender implementations may store Blender objects inside
    `outputs`, while pure Python implementations/tests may
    use ordinary Python objects.

    Example:

        context.set_output(
            PipelineStage.GEOMETRY,
            generated_object,
        )

        mesh = context.require_output(
            PipelineStage.GEOMETRY
        )
    """

    scene: Any = None

    settings: Any = None

    source: Any = None

    outputs: dict[
        PipelineStage,
        Any,
    ] = field(
        default_factory=dict
    )

    metadata: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    def set_output(
        self,
        stage: PipelineStage,
        value: Any,
    ) -> None:
        self.outputs[
            PipelineStage(stage)
        ] = value

    def get_output(
        self,
        stage: PipelineStage,
        default: Any = None,
    ) -> Any:
        return self.outputs.get(
            PipelineStage(stage),
            default,
        )

    def has_output(
        self,
        stage: PipelineStage,
    ) -> bool:
        return (
            PipelineStage(stage)
            in self.outputs
        )

    def require_output(
        self,
        stage: PipelineStage,
    ) -> Any:
        normalized_stage = (
            PipelineStage(stage)
        )

        if (
            normalized_stage
            not in self.outputs
        ):
            raise RuntimeError(
                (
                    "Pipeline stage output "
                    f'"{normalized_stage.value}" '
                    "is required but missing."
                )
            )

        return self.outputs[
            normalized_stage
        ]


# ---------------------------------------------------------
# Execution result
# ---------------------------------------------------------

class StageResultState(
    str,
    Enum,
):
    SUCCESS = "success"

    SKIPPED = "skipped"

    FAILED = "failed"


@dataclass(frozen=True)
class StageExecutionResult:
    """
    Result returned by every implementation.

    Implementations should generally return FAILED only for
    expected product-level failures.

    Unexpected programming errors may still raise exceptions;
    the orchestrator will eventually catch and report them.
    """

    stage: PipelineStage

    implementation_id: str

    state: StageResultState

    payload: Any = None

    message: str = ""

    metrics: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    metadata: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "stage",
            PipelineStage(
                self.stage
            ),
        )

        object.__setattr__(
            self,
            "implementation_id",
            validate_implementation_id(
                self.implementation_id
            ),
        )

        object.__setattr__(
            self,
            "state",
            StageResultState(
                self.state
            ),
        )

    @property
    def success(
        self,
    ) -> bool:
        return (
            self.state
            == StageResultState.SUCCESS
        )

    @property
    def failed(
        self,
    ) -> bool:
        return (
            self.state
            == StageResultState.FAILED
        )

    @property
    def skipped(
        self,
    ) -> bool:
        return (
            self.state
            == StageResultState.SKIPPED
        )

    @classmethod
    def succeeded(
        cls,
        *,
        stage: PipelineStage,
        implementation_id: str,
        payload: Any = None,
        message: str = "",
        metrics: Mapping[
            str,
            Any,
        ]
        | None = None,
        metadata: Mapping[
            str,
            Any,
        ]
        | None = None,
    ) -> "StageExecutionResult":
        return cls(
            stage=stage,
            implementation_id=(
                implementation_id
            ),
            state=(
                StageResultState.SUCCESS
            ),
            payload=payload,
            message=message,
            metrics=(
                metrics
                or {}
            ),
            metadata=(
                metadata
                or {}
            ),
        )

    @classmethod
    def skipped_result(
        cls,
        *,
        stage: PipelineStage,
        implementation_id: str,
        message: str = "",
        metadata: Mapping[
            str,
            Any,
        ]
        | None = None,
    ) -> "StageExecutionResult":
        return cls(
            stage=stage,
            implementation_id=(
                implementation_id
            ),
            state=(
                StageResultState.SKIPPED
            ),
            payload=None,
            message=message,
            metrics={},
            metadata=(
                metadata
                or {}
            ),
        )

    @classmethod
    def failed_result(
        cls,
        *,
        stage: PipelineStage,
        implementation_id: str,
        message: str,
        metadata: Mapping[
            str,
            Any,
        ]
        | None = None,
    ) -> "StageExecutionResult":
        return cls(
            stage=stage,
            implementation_id=(
                implementation_id
            ),
            state=(
                StageResultState.FAILED
            ),
            payload=None,
            message=message,
            metrics={},
            metadata=(
                metadata
                or {}
            ),
        )


# ---------------------------------------------------------
# Implementation contract
# ---------------------------------------------------------

@runtime_checkable
class PipelineImplementation(
    Protocol
):
    """
    Contract implemented by every concrete Meshvenn engine.

    Examples:

        ProjectionInputImplementation

        NativeVisualHullImplementation

        ProjectedColorImplementation

        UVBakeImplementation

        AutoRigImplementation

        GodotExportImplementation

    The orchestrator does not need to know their internals.
    """

    @property
    def descriptor(
        self,
    ) -> ImplementationDescriptor:
        ...

    def availability(
        self,
        context: PipelineContext,
    ) -> ImplementationAvailability:
        ...

    def execute(
        self,
        context: PipelineContext,
    ) -> StageExecutionResult:
        ...


# ---------------------------------------------------------
# Stage selection
# ---------------------------------------------------------

@dataclass(frozen=True)
class PipelineStageSelection:
    """
    Implementation chosen by the user for one stage.
    """

    stage: PipelineStage

    implementation_id: str

    enabled: bool = True

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "stage",
            PipelineStage(
                self.stage
            ),
        )

        object.__setattr__(
            self,
            "implementation_id",
            validate_implementation_id(
                self.implementation_id
            ),
        )


# ---------------------------------------------------------
# Pipeline plan
# ---------------------------------------------------------

@dataclass(frozen=True)
class PipelinePlan:
    """
    Immutable execution plan.

    Selection order is normalized to PIPELINE_STAGE_ORDER.

    A stage can be present but disabled, which allows the UI
    to expose optional stages such as material or rig without
    special-casing the orchestrator.
    """

    selections: tuple[
        PipelineStageSelection,
        ...
    ]

    def __post_init__(
        self,
    ) -> None:
        selection_by_stage: dict[
            PipelineStage,
            PipelineStageSelection,
        ] = {}

        for selection in (
            self.selections
        ):
            if (
                selection.stage
                in selection_by_stage
            ):
                raise ValueError(
                    (
                        "Pipeline plan contains duplicate "
                        f'stage "{selection.stage.value}".'
                    )
                )

            selection_by_stage[
                selection.stage
            ] = selection

        normalized = tuple(
            selection_by_stage[
                stage
            ]
            for stage
            in PIPELINE_STAGE_ORDER
            if stage
            in selection_by_stage
        )

        object.__setattr__(
            self,
            "selections",
            normalized,
        )

    def selection_for(
        self,
        stage: PipelineStage,
    ) -> (
        PipelineStageSelection
        | None
    ):
        normalized_stage = (
            PipelineStage(stage)
        )

        for selection in (
            self.selections
        ):
            if (
                selection.stage
                == normalized_stage
            ):
                return selection

        return None

    def enabled_selection_for(
        self,
        stage: PipelineStage,
    ) -> (
        PipelineStageSelection
        | None
    ):
        selection = (
            self.selection_for(
                stage
            )
        )

        if (
            selection is None
            or not selection.enabled
        ):
            return None

        return selection

    @property
    def enabled_selections(
        self,
    ) -> tuple[
        PipelineStageSelection,
        ...
    ]:
        return tuple(
            selection
            for selection
            in self.selections
            if selection.enabled
        )