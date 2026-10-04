"""Pure policy for selecting a production GLB character route."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .rig_compatibility import SOURCE_RIG_PRESERVATION_TARGET


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
    losses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.route not in GLB_CHARACTER_ROUTES:
            raise ValueError(f"Unknown GLB character route: {self.route}")
        if not self.reason.strip():
            raise ValueError("GLB route decisions require an explicit reason.")
        object.__setattr__(self, "losses", tuple(self.losses))

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "reason": self.reason,
            "source_profile": self.source_profile,
            "source_archetype": self.source_archetype,
            "source_certification": self.source_certification,
            "losses": self.losses,
        }


def decide_glb_character_route(
    *,
    source_skin_count: int,
    source_profile: str | None,
    source_archetype: str = "unknown",
    source_certification: str | None = None,
    compatible_targets: Iterable[str] = (),
    source_animation_count: int = 0,
    source_morph_target_count: int = 0,
) -> GLBRouteDecision:
    """Choose fidelity, standardization, or safe geometry-only export."""
    for value, label in ((source_skin_count, "skin"), (source_animation_count, "animation"),
                         (source_morph_target_count, "morph target")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"GLB {label} count must be a non-negative integer.")
    profile = str(source_profile).strip() if source_profile else None
    archetype = str(source_archetype).strip() or "unknown"
    certification = (
        str(source_certification).strip() if source_certification else None
    )
    targets = frozenset(str(target).strip() for target in compatible_targets)
    losses = tuple(label for count, label in (
        (source_skin_count, "source rig and skin"),
        (source_animation_count, "source animation clips"),
        (source_morph_target_count, "morph targets"),
    ) if count)

    if source_skin_count == 0:
        return GLBRouteDecision(
            GEOMETRY_ONLY_ROUTE,
            "The GLB has no skin, so automatic rig and Motion stages are omitted.",
            profile,
            archetype,
            certification,
            losses,
        )
    if profile and certification == "e2e" and SOURCE_RIG_PRESERVATION_TARGET in targets:
        return GLBRouteDecision(
            PRESERVE_SOURCE_ROUTE,
            "The source rig has an E2E-tested preservation adapter; canonicalization is opt-in.",
            profile,
            archetype,
            certification,
        )
    return GLBRouteDecision(
        GEOMETRY_ONLY_ROUTE,
        "No E2E-tested preservation adapter is registered; geometry-only export is degraded.",
        profile,
        archetype,
        certification,
        losses,
    )


__all__ = (
    "CANONICALIZE_ROUTE",
    "GEOMETRY_ONLY_ROUTE",
    "GLB_CHARACTER_ROUTES",
    "GLBRouteDecision",
    "PRESERVE_SOURCE_ROUTE",
    "decide_glb_character_route",
)
