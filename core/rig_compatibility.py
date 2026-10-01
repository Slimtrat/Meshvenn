"""Pure source-rig classification and target-routing contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable


CANONICAL_BIPED_TARGET = "canonical-biped-v1"
RIG_ARCHETYPES = frozenset({"humanoid", "quadruped", "insufficient", "unknown"})


@dataclass(frozen=True)
class RigStructureEvidence:
    """Engine-neutral measurements captured before source rig data is discarded."""

    armature_count: int
    bone_count: int
    root_bone_count: int
    max_hierarchy_depth: int
    skinned_mesh_count: int
    rest_dimensions: tuple[float, float, float]

    def __post_init__(self) -> None:
        counts = (
            self.armature_count,
            self.bone_count,
            self.root_bone_count,
            self.max_hierarchy_depth,
            self.skinned_mesh_count,
        )
        if any(
            isinstance(value, bool) or int(value) != value or value < 0
            for value in counts
        ):
            raise ValueError("Rig structure counts must be nonnegative integers.")
        dimensions = tuple(float(value) for value in self.rest_dimensions)
        if len(dimensions) != 3 or any(
            not math.isfinite(value) or value < 0.0 for value in dimensions
        ):
            raise ValueError("Rig rest dimensions must contain three finite nonnegative values.")
        object.__setattr__(self, "rest_dimensions", dimensions)

    @property
    def structural_score(self) -> float:
        if self.armature_count != 1:
            return 0.0
        score = (
            0.20
            + 0.20 * min(self.bone_count / 17.0, 1.0)
            + 0.15 * min(self.root_bone_count, 1)
            + 0.15 * min(self.max_hierarchy_depth / 4.0, 1.0)
            + 0.20 * min(self.skinned_mesh_count, 1)
            + 0.10 * (max(self.rest_dimensions) > 1.0e-8)
        )
        return min(max(float(score), 0.0), 1.0)

    @property
    def rest_proportions(self) -> tuple[float, float, float]:
        longest = max(self.rest_dimensions)
        if longest <= 1.0e-8:
            return (0.0, 0.0, 0.0)
        return tuple(value / longest for value in self.rest_dimensions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "armature_count": self.armature_count,
            "bone_count": self.bone_count,
            "root_bone_count": self.root_bone_count,
            "max_hierarchy_depth": self.max_hierarchy_depth,
            "skinned_mesh_count": self.skinned_mesh_count,
            "rest_dimensions": self.rest_dimensions,
            "rest_proportions": self.rest_proportions,
            "structural_score": self.structural_score,
        }


@dataclass(frozen=True)
class RigCompatibilityReport:
    """Semantic classification and one explicit target-routing decision."""

    source_profile: str | None
    source_archetype: str
    classification_confidence: float
    target_rig: str
    target_compatible: bool | None
    semantic_score: float | None
    structure: RigStructureEvidence
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.source_archetype not in RIG_ARCHETYPES:
            raise ValueError(f"Unknown source rig archetype: {self.source_archetype}")
        confidence = float(self.classification_confidence)
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("Rig classification confidence must be inside [0, 1].")
        object.__setattr__(self, "classification_confidence", confidence)
        if self.semantic_score is not None:
            semantic_score = float(self.semantic_score)
            if not math.isfinite(semantic_score) or not 0.0 <= semantic_score <= 1.0:
                raise ValueError("Rig semantic score must be inside [0, 1].")
            object.__setattr__(self, "semantic_score", semantic_score)
        if not self.target_rig.strip():
            raise ValueError("Rig compatibility requires a target rig identifier.")
        if not self.reasons:
            raise ValueError("Rig compatibility requires at least one reason.")

    @property
    def routable(self) -> bool:
        return self.target_compatible is True

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_profile": self.source_profile,
            "source_archetype": self.source_archetype,
            "classification_confidence": self.classification_confidence,
            "target_rig": self.target_rig,
            "target_compatible": self.target_compatible,
            "semantic_score": self.semantic_score,
            "structural_score": self.structure.structural_score,
            "reasons": self.reasons,
            "structure": self.structure.as_dict(),
        }


def assess_rig_compatibility(
    structure: RigStructureEvidence,
    *,
    source_profile: str | None,
    declared_archetype: str | None,
    compatible_targets: Iterable[str] = (),
    target_rig: str = CANONICAL_BIPED_TARGET,
) -> RigCompatibilityReport:
    """Classify a source rig and decide whether it may enter a target rig path."""
    if structure.armature_count == 0:
        return RigCompatibilityReport(
            None,
            "unknown",
            0.0,
            target_rig,
            None,
            None,
            structure,
            ("Source contains no rig; target compatibility is not applicable.",),
        )
    if structure.armature_count != 1:
        return RigCompatibilityReport(
            None,
            "unknown",
            0.0,
            target_rig,
            False,
            0.0,
            structure,
            ("Exactly one source armature is required for deterministic routing.",),
        )
    if source_profile is None or declared_archetype is None:
        confidence = min(structure.bone_count / 17.0, 1.0) * 0.25
        return RigCompatibilityReport(
            None,
            "insufficient",
            confidence,
            target_rig,
            False,
            0.0,
            structure,
            ("The source rig does not match a registered semantic profile.",),
        )
    if declared_archetype not in RIG_ARCHETYPES - {"insufficient", "unknown"}:
        raise ValueError(f"Profiles cannot declare rig archetype: {declared_archetype}")

    targets = frozenset(
        str(value).strip() for value in compatible_targets if str(value).strip()
    )
    compatible = target_rig in targets
    reason = (
        f'Source profile "{source_profile}" is compatible with target "{target_rig}".'
        if compatible
        else (
            f'Source archetype "{declared_archetype}" has no compatible '
            f'target for "{target_rig}".'
        )
    )
    return RigCompatibilityReport(
        source_profile,
        declared_archetype,
        1.0,
        target_rig,
        compatible,
        1.0 if compatible else 0.0,
        structure,
        (reason,),
    )


def require_target_compatibility(
    source_profile: str,
    source_archetype: str,
    compatible_targets: Iterable[str],
    target_rig: str,
) -> None:
    targets = frozenset(compatible_targets)
    if target_rig not in targets:
        raise ValueError(
            f'Source profile "{source_profile}" is {source_archetype} and is not '
            f'compatible with target rig "{target_rig}".'
        )


__all__ = (
    "CANONICAL_BIPED_TARGET",
    "RIG_ARCHETYPES",
    "RigCompatibilityReport",
    "RigStructureEvidence",
    "assess_rig_compatibility",
    "require_target_compatibility",
)
