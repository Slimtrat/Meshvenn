from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable

from .identifiers import validate_implementation_id
from .stages import PipelineStage


@dataclass(frozen=True)
class ImplementationDescriptor:
    identifier: str
    stage: PipelineStage
    label: str
    description: str
    version: str = "1"
    experimental: bool = False
    supports_headless: bool = True
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier", validate_implementation_id(self.identifier))
        object.__setattr__(self, "stage", PipelineStage(self.stage))
        label = str(self.label).strip()
        if not label:
            raise ValueError("Implementation label cannot be empty.")
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "description", str(self.description).strip())
        version = str(self.version).strip()
        if not version:
            raise ValueError("Implementation version cannot be empty.")
        object.__setattr__(self, "version", version)
        normalized: list[str] = []
        seen: set[str] = set()
        for capability in self.capabilities:
            value = str(capability).strip()
            if value and value not in seen:
                seen.add(value)
                normalized.append(value)
        object.__setattr__(self, "capabilities", tuple(normalized))


class AvailabilityState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ImplementationAvailability:
    state: AvailabilityState
    reason: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.state in {AvailabilityState.READY, AvailabilityState.DEGRADED}

    @property
    def ready(self) -> bool:
        return self.state == AvailabilityState.READY

    @classmethod
    def ready_state(cls, *, details: Mapping[str, Any] | None = None) -> "ImplementationAvailability":
        return cls(AvailabilityState.READY, "", details or {})

    @classmethod
    def degraded(cls, reason: str, *, details: Mapping[str, Any] | None = None) -> "ImplementationAvailability":
        return cls(AvailabilityState.DEGRADED, str(reason), details or {})

    @classmethod
    def unavailable(cls, reason: str, *, details: Mapping[str, Any] | None = None) -> "ImplementationAvailability":
        return cls(AvailabilityState.UNAVAILABLE, str(reason), details or {})


@runtime_checkable
class PipelineImplementation(Protocol):
    @property
    def descriptor(self) -> ImplementationDescriptor: ...

    def availability(self, context: "PipelineContext") -> ImplementationAvailability: ...

    def execute(self, context: "PipelineContext") -> "StageExecutionResult": ...


from .context import PipelineContext  # noqa: E402
from .results import StageExecutionResult  # noqa: E402
