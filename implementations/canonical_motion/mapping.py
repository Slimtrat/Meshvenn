"""Pure source-profile detection and semantic bone mapping for motion retargeting."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


CANONICAL_ANIMATED_ROLES = (
    "pelvis",
    "spine",
    "chest",
    "neck",
    "head",
    "upper_arm.L",
    "forearm.L",
    "hand.L",
    "upper_arm.R",
    "forearm.R",
    "hand.R",
    "thigh.L",
    "shin.L",
    "foot.L",
    "thigh.R",
    "shin.R",
    "foot.R",
)


@dataclass(frozen=True)
class MotionSourceProfile:
    identifier: str
    role_to_source_bone: tuple[tuple[str, str], ...]

    @property
    def required_bones(self) -> frozenset[str]:
        return frozenset(bone for _, bone in self.role_to_source_bone)


@dataclass(frozen=True)
class BoneMapEntry:
    role: str
    source_bone: str
    target_bone: str


@dataclass(frozen=True)
class ResolvedBoneMap:
    profile_id: str
    entries: tuple[BoneMapEntry, ...]

    @property
    def source_bone_map(self) -> dict[str, str]:
        """Return the stable public role-to-source mapping stored in MotionOutput."""
        return {entry.role: entry.source_bone for entry in self.entries}

    @property
    def animated_roles(self) -> tuple[str, ...]:
        return tuple(entry.role for entry in self.entries)


RIGGED_FIGURE_PROFILE = MotionSourceProfile(
    identifier="rigged-figure-v1",
    role_to_source_bone=(
        ("pelvis", "torso_joint_1"),
        ("spine", "torso_joint_2"),
        ("chest", "torso_joint_3"),
        ("neck", "neck_joint_1"),
        ("head", "neck_joint_2"),
        ("upper_arm.L", "arm_joint_L_1"),
        ("forearm.L", "arm_joint_L_2"),
        ("hand.L", "arm_joint_L_3"),
        ("upper_arm.R", "arm_joint_R_1"),
        ("forearm.R", "arm_joint_R_2"),
        ("hand.R", "arm_joint_R_3"),
        ("thigh.L", "leg_joint_L_1"),
        ("shin.L", "leg_joint_L_2"),
        ("foot.L", "leg_joint_L_3"),
        ("thigh.R", "leg_joint_R_1"),
        ("shin.R", "leg_joint_R_2"),
        ("foot.R", "leg_joint_R_3"),
    ),
)

SOURCE_PROFILES = (RIGGED_FIGURE_PROFILE,)


def detect_source_profile(bone_names: Iterable[str]) -> MotionSourceProfile:
    """Detect a supported source skeleton from its complete imported bone set."""
    available = {str(name) for name in bone_names}
    matches = [profile for profile in SOURCE_PROFILES if profile.required_bones <= available]
    if not matches:
        missing = sorted(RIGGED_FIGURE_PROFILE.required_bones - available)
        suffix = f" Missing RiggedFigure bones: {', '.join(missing)}." if missing else ""
        raise ValueError(f"Unsupported motion source skeleton.{suffix}")
    if len(matches) > 1:
        identifiers = ", ".join(profile.identifier for profile in matches)
        raise ValueError(f"Ambiguous motion source skeleton: {identifiers}")
    return matches[0]


def resolve_bone_map(
    source_bone_names: Iterable[str],
    target_semantic_bones: Mapping[str, str],
    target_bone_names: Iterable[str],
) -> ResolvedBoneMap:
    """Resolve all 17 animated roles; the canonical root is intentionally fixed."""
    profile = detect_source_profile(source_bone_names)
    target_available = {str(name) for name in target_bone_names}
    semantics = {str(role): str(name) for role, name in target_semantic_bones.items()}
    if "root" not in semantics or semantics["root"] not in target_available:
        raise ValueError("Canonical motion target requires a fixed semantic root bone")

    entries = []
    source_by_role = dict(profile.role_to_source_bone)
    for role in CANONICAL_ANIMATED_ROLES:
        target_name = semantics.get(role)
        if not target_name:
            raise ValueError(f"Canonical motion target is missing semantic role: {role}")
        if target_name not in target_available:
            raise ValueError(f"Canonical motion target bone does not exist: {target_name}")
        entries.append(BoneMapEntry(role, source_by_role[role], target_name))
    return ResolvedBoneMap(profile.identifier, tuple(entries))


__all__ = (
    "CANONICAL_ANIMATED_ROLES",
    "RIGGED_FIGURE_PROFILE",
    "SOURCE_PROFILES",
    "BoneMapEntry",
    "MotionSourceProfile",
    "ResolvedBoneMap",
    "detect_source_profile",
    "resolve_bone_map",
)
