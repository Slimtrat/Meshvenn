"""The only dependency direction between the agent gateway and an engine."""
from __future__ import annotations

from typing import Callable, Protocol


class EnginePort(Protocol):
    def capabilities(self) -> dict:
        """Return schema_version, engine_version and the versioned action mapping."""
        ...

    def execute(self, action: str, arguments: dict, *, cancel: Callable[[], bool] | None = None) -> dict:
        """Execute pure JSON arguments; host construction owns native configuration."""
        ...
