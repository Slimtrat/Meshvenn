"""Immutable source revisions and declared camera/projection provenance."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..projection_alignment import ProjectionAlignment
from ..projection_frame import native_projection_frame
from ..projection_math import ProjectionTransform, compile_projection
from .codec import (JsonContract, fingerprint, positive, require_id,
                    require_sha256, require_text, require_version, unique, validate_model)
from .enums import CameraProjection, ViewOrigin, ViewRole


@dataclass(frozen=True)
class ContentReference(JsonContract):
    """SHA-256 of the original file bytes, with decoded raster dimensions."""

    sha256: str
    width: int
    height: int
    media_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        validate_model(self)
        require_sha256(self.sha256)
        positive(self.width, "width")
        positive(self.height, "height")
        require_text(self.media_type, "media_type")


@dataclass(frozen=True)
class ArtifactReference(JsonContract):
    artifact_id: str
    sha256: str
    media_type: str
    uri: str = ""

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.artifact_id, "artifact_id")
        require_sha256(self.sha256)
        require_text(self.media_type, "media_type")


@dataclass(frozen=True)
class EngineVersion(JsonContract):
    engine_id: str
    version: str

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.engine_id, "engine_id")
        require_text(self.version, "version")


@dataclass(frozen=True)
class DiagnosticPolicy(JsonContract):
    policy_id: str
    version: str
    configuration_sha256: str
    required_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.policy_id, "policy_id")
        require_text(self.version, "version")
        require_sha256(self.configuration_sha256, "configuration_sha256")
        unique(self.required_checks, "required_checks")
        for code in self.required_checks:
            validate_code(code)
        object.__setattr__(self, "required_checks", tuple(sorted(self.required_checks)))


def validate_code(code: str) -> None:
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", code):
        raise ValueError("A finding/check code must be a stable lowercase dotted identifier.")


@dataclass(frozen=True)
class DiagnosticResolution(JsonContract):
    width: int
    height: int
    depth: int = 1
    unit: str = "pixel"

    def __post_init__(self) -> None:
        validate_model(self)
        for name in ("width", "height", "depth"):
            positive(getattr(self, name), name)
        require_text(self.unit, "unit")


@dataclass(frozen=True)
class CameraDeclaration(JsonContract):
    """A declaration is not calibration; verification requires hashed evidence.

    Angles and Flip X use the existing native ProjectionTransform convention.
    Perspective and unknown declarations remain representable, never certified
    by the current orthographic engine.
    """

    projection: CameraProjection
    azimuth_degrees: float | None = None
    elevation_degrees: float | None = None
    flip_x: bool = False
    verified: bool = False
    verification_evidence: ArtifactReference | None = None

    def __post_init__(self) -> None:
        validate_model(self)
        if self.verified and (self.projection != CameraProjection.ORTHOGRAPHIC
                              or self.azimuth_degrees is None or self.elevation_degrees is None
                              or self.verification_evidence is None):
            raise ValueError("Verified cameras require supported angles and hashed verification evidence.")

    @property
    def transform(self) -> ProjectionTransform:
        if (self.projection != CameraProjection.ORTHOGRAPHIC
                or self.azimuth_degrees is None or self.elevation_degrees is None):
            raise ValueError("No supported orthographic projection transform is declared.")
        return compile_projection(azimuth_degrees=self.azimuth_degrees,
                                  elevation_degrees=self.elevation_degrees, flip_x=self.flip_x)

    def native_frame(self, side: float, width: int, height: int) -> tuple[float, float]:
        # Reuse the frame authority; never derive a second camera convention.
        self.transform
        return native_projection_frame(side, self.azimuth_degrees, self.elevation_degrees, width, height)


@dataclass(frozen=True)
class ViewRevision(JsonContract):
    view_id: str
    revision: int
    image: ContentReference | None
    mask: ContentReference | None
    camera: CameraDeclaration
    alignment: ProjectionAlignment = field(default_factory=ProjectionAlignment)
    role: ViewRole = ViewRole.OBSERVATION
    origin: ViewOrigin = ViewOrigin.USER
    derived_from: tuple[str, ...] = ()
    origin_details: str = ""

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.view_id, "view_id")
        positive(self.revision, "revision")
        unique(self.derived_from, "derived_from")
        for digest in self.derived_from:
            require_sha256(digest, "derived_from")
        if self.origin == ViewOrigin.DERIVED and not self.derived_from:
            raise ValueError("Derived views must retain original content hashes.")


@dataclass(frozen=True)
class CanonicalReference(JsonContract):
    reference_id: str
    revision: int
    content: ContentReference
    validated: bool = False
    view_ids: tuple[str, ...] = ()
    validation_evidence: ArtifactReference | None = None

    def __post_init__(self) -> None:
        validate_model(self)
        require_id(self.reference_id, "reference_id")
        positive(self.revision, "revision")
        unique(self.view_ids, "canonical view_ids")
        for view_id in self.view_ids:
            require_id(view_id, "canonical view_id")
        object.__setattr__(self, "view_ids", tuple(sorted(self.view_ids)))


@dataclass(frozen=True)
class ViewSetRevision(JsonContract):
    view_set_id: str
    revision: int
    views: tuple[ViewRevision, ...]
    canonical_reference: CanonicalReference | None = None
    input_order: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        validate_model(self)
        require_version(self.schema_version)
        require_id(self.view_set_id, "view_set_id")
        positive(self.revision, "revision")
        ids = tuple(view.view_id for view in self.views)
        unique(ids, "view IDs")
        if not self.input_order:
            object.__setattr__(self, "input_order", ids)
        if len(self.input_order) != len(ids) or set(self.input_order) != set(ids):
            raise ValueError("input_order must be a permutation of the view IDs.")
        if self.canonical_reference and not set(self.canonical_reference.view_ids) <= set(ids):
            raise ValueError("Canonical reference view IDs must belong to the view set.")
        object.__setattr__(self, "views", tuple(sorted(self.views, key=lambda v: v.view_id)))

    def dependency_dict(self) -> dict:
        data = self.to_dict()
        del data["input_order"]
        # Artifact locations are retrieval provenance, not content dependencies.
        # Moving an unchanged proof must not invalidate its verified camera.
        def semantic(value):
            if isinstance(value, dict):
                return {key: semantic(item) for key, item in value.items() if key != "uri"}
            if isinstance(value, list):
                return [semantic(item) for item in value]
            return value
        return semantic(data)

    @property
    def dependency_fingerprint(self) -> str:
        return fingerprint(self.dependency_dict())
