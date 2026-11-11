"""Version-one vocabulary. Finding codes remain extensible dotted identifiers."""

from enum import Enum


class VerificationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class Category(str, Enum):
    INPUT = "input"
    CAMERA = "camera"
    ALIGNMENT = "alignment"
    GEOMETRY = "geometry"
    APPEARANCE = "appearance"
    COVERAGE = "coverage"
    ENGINE = "engine"
    QUALITY = "quality"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


class CompletionState(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ViewOrigin(str, Enum):
    USER = "user"
    RENDERED = "rendered"
    GENERATED = "generated"
    DERIVED = "derived"


class ViewRole(str, Enum):
    OBSERVATION = "observation"
    REFERENCE = "reference"
    CONTROL = "control"


class CameraProjection(str, Enum):
    ORTHOGRAPHIC = "orthographic"
    PERSPECTIVE = "perspective"
    UNKNOWN = "unknown"


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    ARTIFACT = "artifact"
    EXECUTION = "execution"


class JudgmentKind(str, Enum):
    INFERENCE = "inference"
    MODEL = "model"


class ActionKind(str, Enum):
    INSPECT_INPUT = "inspect_input"
    REPAIR_MASK = "repair_mask"
    PROVIDE_VIEW = "provide_view"
    VERIFY_CAMERA = "verify_camera"
    SELECT_REFERENCE = "select_reference"
    APPLY_ALIGNMENT = "apply_alignment"
    REVIEW_REFERENCE = "review_reference"
    REGENERATE_REGION = "regenerate_region"
    DIAGNOSE_ENGINE = "diagnose_engine"


class ThresholdOperator(str, Enum):
    LT = "<"
    LE = "<="
    EQ = "=="
    GE = ">="
    GT = ">"
