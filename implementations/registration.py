from __future__ import annotations

from ..core.pipeline_contracts import PipelineImplementation
from ..core.pipeline_registry import PIPELINE_REGISTRY
from .catalog import (
    BUILTIN_DEFAULT_IMPLEMENTATION_IDS,
    instantiate_builtin_implementations,
    validate_builtin_catalog,
)

_registered_implementation_ids: list[str] = []


def _apply_builtin_defaults() -> None:
    for stage, implementation_id in BUILTIN_DEFAULT_IMPLEMENTATION_IDS.items():
        PIPELINE_REGISTRY.set_default(stage, implementation_id)


def register_builtin_implementations(
    *, replace: bool = True
) -> tuple[PipelineImplementation, ...]:
    """Atomically validate, then register the ordered built-in catalog."""

    implementations = instantiate_builtin_implementations()
    validate_builtin_catalog(implementations)
    registered: list[PipelineImplementation] = []
    current_ids: list[str] = []
    for implementation in implementations:
        descriptor = implementation.descriptor
        PIPELINE_REGISTRY.register(implementation, default=False, replace=replace)
        registered.append(implementation)
        current_ids.append(descriptor.identifier)

    stale_ids = [
        implementation_id
        for implementation_id in _registered_implementation_ids
        if implementation_id not in current_ids
    ]
    for implementation_id in stale_ids:
        PIPELINE_REGISTRY.unregister(implementation_id)

    _apply_builtin_defaults()
    _registered_implementation_ids.clear()
    _registered_implementation_ids.extend(current_ids)
    return tuple(registered)


def unregister_builtin_implementations() -> None:
    """Remove only implementations owned by Meshvenn, in reverse order."""

    for implementation_id in reversed(_registered_implementation_ids):
        PIPELINE_REGISTRY.unregister(implementation_id)
    _registered_implementation_ids.clear()


def register() -> None:
    register_builtin_implementations(replace=True)


def unregister() -> None:
    unregister_builtin_implementations()


def registered_builtin_ids() -> tuple[str, ...]:
    return tuple(_registered_implementation_ids)


def builtin_implementation_count() -> int:
    return len(_registered_implementation_ids)
