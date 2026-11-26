"""Finite profile contracts; measured checks never imply general certification."""

from dataclasses import asdict, dataclass
import hashlib, json, math, re

LIMITS = {
    "source_structure_changes": ("max", 0.0),
    "invalid_weights": ("max", 0.0),
    "export_failures": ("max", 0.0),
    "appearance_transport_changes": ("max", 0.0),
    "rest_position_error": ("max", 2e-5),
    "proximal_link_error": ("max", 0.01),
    "distal_link_error": ("max", 0.01),
    "protected_elbow_error": ("max", 0.001),
    "shoulder_link_error": ("max", 0.02),
    "protected_shoulder_error": ("max", 0.001),
    "elbow_radius_retention": ("min", 0.65),
    "elbow_area_retention": ("min", 0.05),
    "elbow_inverted_area_fraction": ("max", 0.0),
}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class Budget:
    max_attempts: int = 4
    max_elapsed_seconds: float = 180.0
    max_stagnation: int = 2

    def __post_init__(self):
        if (
            type(self.max_attempts) is not int
            or not 1 <= self.max_attempts <= 8
            or type(self.max_stagnation) is not int
            or not 1 <= self.max_stagnation <= 8
            or not finite(self.max_elapsed_seconds)
            or not 1 <= self.max_elapsed_seconds <= 3600
        ):
            raise ValueError("Invalid humanoid loop budget")


@dataclass(frozen=True)
class Asset:
    id: str
    sha256: str

    def __post_init__(self):
        if not re.fullmatch(r"[a-z0-9_-]{1,80}", self.id) or not re.fullmatch(
            "[a-f0-9]{64}", self.sha256
        ):
            raise ValueError("Invalid immutable asset reference")


@dataclass(frozen=True)
class Assessment:
    asset: Asset
    measurements: dict
    evidence: dict

    def __post_init__(self):
        if set(self.measurements) != set(LIMITS):
            raise ValueError("Missing or additional profile measurement")
        if any(
            v is not None and (not finite(v) or v < 0)
            for v in self.measurements.values()
        ):
            raise ValueError(
                "Measurements must be nonnegative finite numbers or unknown"
            )
        json.dumps(self.evidence, allow_nan=False)

    @property
    def checks(self):
        return {
            n: (
                "unknown"
                if self.measurements[n] is None
                else (
                    "pass"
                    if (
                        self.measurements[n] <= limit
                        if direction == "max"
                        else self.measurements[n] >= limit
                    )
                    else "fail"
                )
            )
            for n, (direction, limit) in LIMITS.items()
        }

    @property
    def passed(self):
        return all(s == "pass" for s in self.checks.values())

    @property
    def preservation_passed(self):
        return all(
            self.checks[n] == "pass"
            for n in (
                "source_structure_changes",
                "invalid_weights",
                "export_failures",
                "appearance_transport_changes",
                "rest_position_error",
            )
        )

    @property
    def rank(self):
        statuses = self.checks
        return (
            sum(s != "pass" for s in statuses.values()),
            sum(
                (
                    1e6
                    if self.measurements[n] is None
                    else (
                        max(0.0, self.measurements[n] / max(limit, 1e-9) - 1.0)
                        if direction == "max"
                        else max(0.0, limit / max(self.measurements[n], 1e-9) - 1.0)
                    )
                )
                for n, (direction, limit) in LIMITS.items()
            ),
        )

    def to_dict(self):
        return dict(
            asset=asdict(self.asset),
            measurements=self.measurements,
            checks=self.checks,
            evidence=self.evidence,
        )


def policy_fingerprint(budget):
    value = dict(
        profile="native-humanoid-deformation-v1",
        limits=LIMITS,
        budget=asdict(budget),
        measurement_policy="fixed-source-capsule-regions-v1",
        regeneration_policy="longitudinal-local-arm-chains-v2",
    )
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
