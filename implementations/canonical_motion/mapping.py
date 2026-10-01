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
    certification: str = "contract"
    fixture: str | None = None

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Source profiles require a nonempty identifier")
        roles = tuple(role for role, _ in self.role_to_source_bone)
        if roles != CANONICAL_ANIMATED_ROLES:
            raise ValueError("Source profiles must map the 17 canonical roles in order")
        names = tuple(str(name).strip() for _, name in self.role_to_source_bone)
        if any(not name for name in names) or len(names) != len(set(names)):
            raise ValueError("Source profiles require unique nonempty bone names")
        if self.certification not in {"contract", "e2e"}:
            raise ValueError(f"Unknown source-profile certification: {self.certification}")
        if self.certification == "e2e" and not self.fixture:
            raise ValueError("E2E-certified source profiles require a fixture name")

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
    certification="e2e",
    fixture="RiggedFigure.glb",
)

KHRONOS_FOX_PROFILE = MotionSourceProfile(
    identifier="khronos-fox-v1",
    role_to_source_bone=(
        ("pelvis", "b_Hip_01"),
        ("spine", "b_Spine01_02"),
        ("chest", "b_Spine02_03"),
        ("neck", "b_Neck_04"),
        ("head", "b_Head_05"),
        ("upper_arm.L", "b_LeftUpperArm_09"),
        ("forearm.L", "b_LeftForeArm_010"),
        ("hand.L", "b_LeftHand_011"),
        ("upper_arm.R", "b_RightUpperArm_06"),
        ("forearm.R", "b_RightForeArm_07"),
        ("hand.R", "b_RightHand_08"),
        ("thigh.L", "b_LeftLeg01_015"),
        ("shin.L", "b_LeftLeg02_016"),
        ("foot.L", "b_LeftFoot01_017"),
        ("thigh.R", "b_RightLeg01_019"),
        ("shin.R", "b_RightLeg02_020"),
        ("foot.R", "b_RightFoot01_021"),
    ),
    certification="e2e",
    fixture="Fox.glb",
)

THREEJS_ROBOT_EXPRESSIVE_PROFILE = MotionSourceProfile(
    identifier="threejs-robot-expressive-v1",
    role_to_source_bone=(
        ("pelvis", "Hips"),
        ("spine", "Abdomen"),
        ("chest", "Torso"),
        ("neck", "Neck"),
        ("head", "Head"),
        ("upper_arm.L", "UpperArm.L"),
        ("forearm.L", "LowerArm.L"),
        ("hand.L", "Palm2.L"),
        ("upper_arm.R", "UpperArm.R"),
        ("forearm.R", "LowerArm.R"),
        ("hand.R", "Palm2.R"),
        ("thigh.L", "UpperLeg.L"),
        ("shin.L", "LowerLeg.L"),
        ("foot.L", "Foot.L"),
        ("thigh.R", "UpperLeg.R"),
        ("shin.R", "LowerLeg.R"),
        ("foot.R", "Foot.R"),
    ),
    certification="e2e",
    fixture="RobotExpressive.glb",
)

MIXAMO_HUMANOID_PROFILE = MotionSourceProfile(
    identifier="mixamo-humanoid-v1",
    role_to_source_bone=(
        ("pelvis", "Hips"),
        ("spine", "Spine"),
        ("chest", "Spine2"),
        ("neck", "Neck"),
        ("head", "Head"),
        ("upper_arm.L", "LeftArm"),
        ("forearm.L", "LeftForeArm"),
        ("hand.L", "LeftHand"),
        ("upper_arm.R", "RightArm"),
        ("forearm.R", "RightForeArm"),
        ("hand.R", "RightHand"),
        ("thigh.L", "LeftUpLeg"),
        ("shin.L", "LeftLeg"),
        ("foot.L", "LeftFoot"),
        ("thigh.R", "RightUpLeg"),
        ("shin.R", "RightLeg"),
        ("foot.R", "RightFoot"),
    ),
)

UNREAL_MANNEQUIN_PROFILE = MotionSourceProfile(
    identifier="unreal-mannequin-v1",
    role_to_source_bone=(
        ("pelvis", "pelvis"),
        ("spine", "spine_01"),
        ("chest", "spine_03"),
        ("neck", "neck_01"),
        ("head", "head"),
        ("upper_arm.L", "upperarm_l"),
        ("forearm.L", "lowerarm_l"),
        ("hand.L", "hand_l"),
        ("upper_arm.R", "upperarm_r"),
        ("forearm.R", "lowerarm_r"),
        ("hand.R", "hand_r"),
        ("thigh.L", "thigh_l"),
        ("shin.L", "calf_l"),
        ("foot.L", "foot_l"),
        ("thigh.R", "thigh_r"),
        ("shin.R", "calf_r"),
        ("foot.R", "foot_r"),
    ),
)

MESHVENN_CANONICAL_PROFILE = MotionSourceProfile(
    identifier="meshvenn-canonical-v1",
    role_to_source_bone=tuple((role, role) for role in CANONICAL_ANIMATED_ROLES),
)

SOURCE_PROFILES = (
    RIGGED_FIGURE_PROFILE,
    KHRONOS_FOX_PROFILE,
    THREEJS_ROBOT_EXPRESSIVE_PROFILE,
    MIXAMO_HUMANOID_PROFILE,
    UNREAL_MANNEQUIN_PROFILE,
    MESHVENN_CANONICAL_PROFILE,
)


def _bone_key(name: str) -> str:
    """Normalize case, separators and a glTF/FBX namespace without guessing roles."""
    leaf = str(name).strip().rsplit(":", 1)[-1]
    return "".join(character.casefold() for character in leaf if character.isalnum())


def _available_bones(bone_names: Iterable[str]) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for raw_name in bone_names:
        name = str(raw_name).strip()
        if name:
            grouped.setdefault(_bone_key(name), []).append(name)
    return {key: tuple(sorted(set(names))) for key, names in grouped.items()}


def _profile_source_map(
    profile: MotionSourceProfile,
    available: Mapping[str, tuple[str, ...]],
) -> dict[str, str] | None:
    resolved: dict[str, str] = {}
    for role, expected_name in profile.role_to_source_bone:
        candidates = available.get(_bone_key(expected_name), ())
        if len(candidates) != 1:
            return None
        resolved[role] = candidates[0]
    if len(set(resolved.values())) != len(resolved):
        return None
    return resolved


def detect_source_profile(bone_names: Iterable[str]) -> MotionSourceProfile:
    """Detect a supported source skeleton from its complete imported bone set."""
    available = _available_bones(bone_names)
    matches = [
        profile for profile in SOURCE_PROFILES
        if _profile_source_map(profile, available) is not None
    ]
    if not matches:
        ranked = sorted(
            SOURCE_PROFILES,
            key=lambda profile: sum(
                _bone_key(name) in available for name in profile.required_bones
            ),
            reverse=True,
        )
        closest = ranked[0]
        missing = [
            name for name in closest.required_bones
            if _bone_key(name) not in available
        ]
        matched = len(closest.required_bones) - len(missing)
        raise ValueError(
            "Unsupported motion source skeleton. "
            f'Closest profile "{closest.identifier}" matches '
            f"{matched}/{len(closest.required_bones)} roles; "
            f"missing bones: {', '.join(sorted(missing))}."
        )
    if len(matches) > 1:
        identifiers = ", ".join(profile.identifier for profile in matches)
        raise ValueError(f"Ambiguous motion source skeleton: {identifiers}")
    return matches[0]


def validate_target_rig(
    target_semantic_bones: Mapping[str, str],
    target_bone_names: Iterable[str],
) -> dict[str, str]:
    """Validate the canonical target independently from any source profile."""
    target_available = {str(name) for name in target_bone_names}
    semantics = {str(role): str(name) for role, name in target_semantic_bones.items()}
    if "root" not in semantics or semantics["root"] not in target_available:
        raise ValueError("Canonical motion target requires a fixed semantic root bone")
    for role in CANONICAL_ANIMATED_ROLES:
        target_name = semantics.get(role)
        if not target_name:
            raise ValueError(f"Canonical motion target is missing semantic role: {role}")
        if target_name not in target_available:
            raise ValueError(f"Canonical motion target bone does not exist: {target_name}")
    return semantics


def resolve_bone_map(
    source_bone_names: Iterable[str],
    target_semantic_bones: Mapping[str, str],
    target_bone_names: Iterable[str],
) -> ResolvedBoneMap:
    """Resolve all 17 animated roles; the canonical root is intentionally fixed."""
    source_names = tuple(str(name) for name in source_bone_names)
    available = _available_bones(source_names)
    profile = detect_source_profile(source_names)
    source_by_role = _profile_source_map(profile, available)
    if source_by_role is None:  # pragma: no cover - guarded by detection
        raise RuntimeError(f'Profile "{profile.identifier}" could not be resolved')
    semantics = validate_target_rig(target_semantic_bones, target_bone_names)

    entries = []
    for role in CANONICAL_ANIMATED_ROLES:
        target_name = semantics.get(role)
        entries.append(BoneMapEntry(role, source_by_role[role], target_name))
    return ResolvedBoneMap(profile.identifier, tuple(entries))


__all__ = (
    "CANONICAL_ANIMATED_ROLES",
    "KHRONOS_FOX_PROFILE",
    "MESHVENN_CANONICAL_PROFILE",
    "MIXAMO_HUMANOID_PROFILE",
    "RIGGED_FIGURE_PROFILE",
    "SOURCE_PROFILES",
    "THREEJS_ROBOT_EXPRESSIVE_PROFILE",
    "UNREAL_MANNEQUIN_PROFILE",
    "BoneMapEntry",
    "MotionSourceProfile",
    "ResolvedBoneMap",
    "detect_source_profile",
    "resolve_bone_map",
    "validate_target_rig",
)
