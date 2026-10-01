"""Pure policy for selecting a production GLB character route."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .rig_compatibility import CANONICAL_BIPED_TARGET, SOURCE_RIG_PRESERVATION_TARGET


PRESERVE_SOURCE_ROUTE = "preserve-source"
CANONICALIZE_ROUTE = "canonicalize"
GEOMETRY_ONLY_ROUTE = "geometry-only"
GLB_CHARACTER_ROUTES = frozenset({
    PRESERVE_SOURCE_ROUTE,
    CANONICALIZE_ROUTE,
    GEOMETRY_ONLY_ROUTE,
})


@dataclass(frozen=True)
class GLBRouteDecision:
    route: str
    reason: str
    source_profile: str | None
    source_archetype: str
    source_certification: str | None

    def __post_init__(self) -> None:
        if self.route not in GLB_CHARACTER_ROUTES:
            raise ValueError(f"Unknown GLB character route: {self.route}")
        if not self.reason.strip():
            raise ValueError("GLB route decisions require an explicit reason.")

    def as_dict(self) -> dict[str, str | None]:
        return {
            "route": self.route,
            "reason": self.reason,
            "source_profile": self.source_profile,
            "source_archetype": self.source_archetype,
            "source_certification": self.source_certification,
        }


def decide_glb_character_route(
    *,
    source_skin_count: int,
    source_profile: str | None,
    source_archetype: str = "unknown",
    source_certification: str | None = None,
    compatible_targets: Iterable[str] = (),
) -> GLBRouteDecision:
    """Choose fidelity, standardization, or safe geometry-only export."""
    if source_skin_count < 0:
        raise ValueError("GLB skin count cannot be negative.")
    profile = str(source_profile).strip() if source_profile else None
    archetype = str(source_archetype).strip() or "unknown"
    certification = (
        str(source_certification).strip() if source_certification else None
    )
    targets = frozenset(str(target).strip() for target in compatible_targets)

    if source_skin_count == 0:
        return GLBRouteDecision(
            GEOMETRY_ONLY_ROUTE,
            "The GLB has no skin, so automatic rig and Motion stages are omitted.",
            profile,
            archetype,
            certification,
        )
    if archetype == "humanoid" and CANONICAL_BIPED_TARGET in targets:
        return GLBRouteDecision(
            CANONICALIZE_ROUTE,
            "A supported humanoid is standardized on Canonical Biped V1.",
            profile,
            archetype,
            certification,
        )
    if SOURCE_RIG_PRESERVATION_TARGET in targets:
        return GLBRouteDecision(
            PRESERVE_SOURCE_ROUTE,
            "The source rig has a certified preservation adapter for its archetype.",
            profile,
            archetype,
            certification,
        )
    return GLBRouteDecision(
        GEOMETRY_ONLY_ROUTE,
        "No semantically safe automatic rig target is registered for this GLB.",
        profile,
        archetype,
        certification,
    )


__all__ = (
    "CANONICALIZE_ROUTE",
    "GEOMETRY_ONLY_ROUTE",
    "GLB_CHARACTER_ROUTES",
    "GLBRouteDecision",
    "PRESERVE_SOURCE_ROUTE",
    "decide_glb_character_route",
)
