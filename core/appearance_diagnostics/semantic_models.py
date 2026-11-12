"""Strict immutable data for the optional semantic adapter boundary.

These are model judgments, not deterministic geometry/identity certificates.
No provider, network client, filesystem resolver or serialized callable lives here.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from ..diagnostic_contracts import ArtifactReference, ContentReference, EngineVersion, Finding, Region, ViewSetRevision
from ..diagnostic_contracts.codec import (JsonContract, canonical_json, fingerprint, require_id,
                                         require_sha256, require_text, require_version, unique, validate_model)

KINDS = ("identity", "accessory", "motif")
SEMANTIC_ENGINE = EngineVersion("meshvenn.appearance_semantics", "1.0.0")


def _snapshot_digest(view_id, source, original_decoded_sha256, source_width, source_height,
                     width, height, rgba, color_space, sampling, coordinate_space):
    header = dict(view_id=view_id, source=source.to_dict(), original_decoded_sha256=original_decoded_sha256,
                  source_width=source_width, source_height=source_height, width=width, height=height,
                  color_space=color_space, sampling=sampling, coordinate_space=coordinate_space,
                  encoding="bottom-left-straight-alpha-rgba-f64-be-v1")
    digest = hashlib.sha256(canonical_json(header).encode("utf-8"))
    for value in rgba:
        digest.update(struct.pack(">d", value))
    return digest.hexdigest()


@dataclass(frozen=True)
class SemanticImageSnapshot(JsonContract):
    view_id: str
    source: ContentReference
    original_decoded_sha256: str
    source_width: int
    source_height: int
    width: int
    height: int
    rgba: tuple[float, ...]
    color_space: str
    sampling: str
    coordinate_space: str
    sha256: str

    def __post_init__(self):
        validate_model(self)
        require_id(self.view_id, "semantic image view_id")
        require_sha256(self.original_decoded_sha256, "original decoded hash")
        require_sha256(self.sha256, "derived semantic image hash")
        if (self.source_width, self.source_height) != (self.source.width, self.source.height):
            raise ValueError("Semantic source dimensions must agree with the original content reference.")
        if not 0 < self.source_width*self.source_height <= 1_048_576:
            raise ValueError("A semantic source exceeds the original decoded pixel profile.")
        if not (1 <= self.width <= min(128, self.source_width) and 1 <= self.height <= min(128, self.source_height)):
            raise ValueError("Semantic snapshots must be derived without upsampling, within 128 pixels per axis.")
        if abs(self.width*self.source_height-self.height*self.source_width) > max(self.source_width, self.source_height):
            raise ValueError("A full-frame semantic snapshot must preserve source aspect ratio within pixel quantization.")
        if len(self.rgba) != self.width*self.height*4 or any(not 0 <= value <= 1 for value in self.rgba):
            raise ValueError("Semantic snapshots require finite normalized straight-alpha RGBA.")
        if self.color_space not in ("sRGB", "scene-linear") or self.sampling != "nearest-endpoint-grid" or self.coordinate_space != "source":
            raise ValueError("Semantic snapshots use declared source-space endpoint sampling and supported color encoding.")
        if self.sha256 != _snapshot_digest(self.view_id, self.source, self.original_decoded_sha256,
                self.source_width, self.source_height, self.width, self.height, self.rgba,
                self.color_space, self.sampling, self.coordinate_space):
            raise ValueError("The derived semantic snapshot does not match its content hash.")


def make_semantic_image(*, view_id: str, source: ContentReference, original_decoded_sha256: str,
                        source_width: int, source_height: int, width: int, height: int, rgba,
                        color_space: str = "sRGB", sampling: str = "nearest-endpoint-grid",
                        coordinate_space: str = "source") -> SemanticImageSnapshot:
    """Hash an already-derived host buffer; no decoding, resizing or alignment."""
    values = tuple(rgba)
    if any(type(value) not in (int, float) for value in values):
        raise ValueError("Semantic RGBA channels must be numbers, not booleans or objects.")
    values = tuple(float(value) for value in values)
    # Normalize signed zero exactly as the shared finite JSON codec does.
    values = tuple(0.0 if value == 0 else value for value in values)
    digest = _snapshot_digest(view_id, source, original_decoded_sha256, source_width, source_height,
                              width, height, values, color_space, sampling, coordinate_space)
    return SemanticImageSnapshot(view_id, source, original_decoded_sha256, source_width, source_height,
                                 width, height, values, color_space, sampling, coordinate_space, digest)


@dataclass(frozen=True)
class SemanticRegionPair(JsonContract):
    pair_id: str
    target: Region
    reference: Region
    target_image_sha256: str
    reference_image_sha256: str
    target_visibility: str
    reference_visibility: str
    evidence_sha256: str
    reference_lineage: str
    visible_samples: int = 0

    def __post_init__(self):
        validate_model(self)
        require_id(self.pair_id, "semantic pair_id")
        for digest in (self.target_image_sha256, self.reference_image_sha256, self.evidence_sha256):
            require_sha256(digest)
        if any(value not in ("visible", "hidden", "unknown") for value in (self.target_visibility, self.reference_visibility)):
            raise ValueError("Semantic visibility must be explicit visible/hidden/unknown.")
        if self.reference_lineage not in ("accepted", "target_derived", "circular", "unknown"):
            raise ValueError("Semantic reference lineage must be explicit.")
        if not 0 <= self.visible_samples <= 1_048_576:
            raise ValueError("Semantic visible-sample evidence exceeds the bounded profile.")


@dataclass(frozen=True)
class SemanticRequest(JsonContract):
    view_set: ViewSetRevision
    context_sha256: str
    pairs: tuple[SemanticRegionPair, ...]
    images: tuple[SemanticImageSnapshot, ...]
    kinds: tuple[str, ...] = KINDS
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        require_sha256(self.context_sha256, "appearance context hash")
        unique(tuple(pair.pair_id for pair in self.pairs), "semantic pair IDs")
        unique(tuple(image.view_id for image in self.images), "semantic image view IDs")
        unique(self.kinds, "semantic claim kinds")
        if not self.kinds or any(kind not in KINDS for kind in self.kinds):
            raise ValueError("The request contains unsupported semantic kinds.")
        if len(self.pairs) > 128 or len(self.images) > 20:
            raise ValueError("Semantic requests permit at most 128 pairs and 20 derived images.")
        object.__setattr__(self, "pairs", tuple(sorted(self.pairs, key=lambda pair: pair.pair_id)))
        object.__setattr__(self, "images", tuple(sorted(self.images, key=lambda image: image.view_id)))
        object.__setattr__(self, "kinds", tuple(sorted(self.kinds)))

    @property
    def dependency_fingerprint(self):
        # Source acquisition order is provenance, not semantic truth evidence.
        return fingerprint(dict(schema_version=1, view_set=self.view_set.dependency_dict(),
            context_sha256=self.context_sha256, pairs=[pair.to_dict() for pair in self.pairs],
            images=[dict(view_id=image.view_id, sha256=image.sha256) for image in self.images], kinds=list(self.kinds)))


@dataclass(frozen=True)
class SemanticAnalyzerMetadata(JsonContract):
    analyzer: EngineVersion
    model: EngineVersion
    qualification_evidence: ArtifactReference | None = None
    qualification_kinds: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        if self.analyzer.engine_id == self.model.engine_id and self.analyzer != self.model:
            raise ValueError("One engine identifier cannot declare conflicting adapter/model versions.")
        unique(self.qualification_kinds, "qualified semantic kinds")
        if any(kind not in KINDS for kind in self.qualification_kinds):
            raise ValueError("Qualification evidence declares an unsupported semantic kind.")
        if self.qualification_kinds and self.qualification_evidence is None:
            raise ValueError("Qualified semantic kinds require explicit host qualification evidence.")
        object.__setattr__(self, "qualification_kinds", tuple(sorted(self.qualification_kinds)))


@dataclass(frozen=True)
class SemanticClaim(JsonContract):
    claim_id: str
    pair_id: str
    kind: str
    verdict: str
    target: Region
    reference: Region
    explanation: str
    uncertainty: str
    support: str = "sufficient"
    confidence: float | None = None

    def __post_init__(self):
        validate_model(self)
        require_id(self.claim_id, "semantic claim ID")
        require_id(self.pair_id, "semantic pair ID")
        if self.kind not in KINDS or self.verdict not in ("consistent", "changed", "unknown"):
            raise ValueError("Unsupported semantic claim kind/verdict.")
        if self.support not in ("sufficient", "limited", "none"):
            raise ValueError("Semantic claim support must be explicit.")
        require_text(self.explanation, "semantic explanation")
        require_text(self.uncertainty, "semantic uncertainty")
        if len(self.explanation) > 2048 or len(self.uncertainty) > 1024:
            raise ValueError("Semantic explanation/uncertainty exceeds the bounded response profile.")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Model confidence must be finite in [0,1] and is uncalibrated.")


@dataclass(frozen=True)
class SemanticResponse(JsonContract):
    request_fingerprint: str
    model: EngineVersion
    claims: tuple[SemanticClaim, ...]
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        require_sha256(self.request_fingerprint, "semantic request fingerprint")
        unique(tuple(claim.claim_id for claim in self.claims), "semantic claim IDs")
        if len(self.claims) > 512:
            raise ValueError("Semantic responses permit at most 512 claims.")
        object.__setattr__(self, "claims", tuple(sorted(self.claims, key=lambda claim: claim.claim_id)))


@dataclass(frozen=True)
class SemanticPolicy(JsonContract):
    min_visible_samples: int = 16
    min_region_pixels: int = 16
    min_region_extent: int = 2
    min_confidence: float | None = 0.5
    max_request_bytes: int = 33_554_432
    max_response_bytes: int = 524_288
    max_timeout_seconds: float = 120.0
    required: bool = False

    def __post_init__(self):
        validate_model(self)
        if not (1 <= self.min_visible_samples <= 1_048_576 and 1 <= self.min_region_pixels <= 16384 and
                1 <= self.min_region_extent <= 128 and 1024 <= self.max_request_bytes <= 67_108_864 and
                1024 <= self.max_response_bytes <= 2_097_152 and 0 < self.max_timeout_seconds <= 120):
            raise ValueError("Semantic policy exceeds its bounded static image profile.")
        if self.min_confidence is not None and not 0 <= self.min_confidence <= 1:
            raise ValueError("An uncalibrated confidence abstention floor must be in [0,1].")

    @property
    def configuration_sha256(self):
        return fingerprint(self.to_dict())


@dataclass(frozen=True)
class EvaluatedSemanticClaim(JsonContract):
    pair_id: str
    kind: str
    status: str
    reason: str
    claims: tuple[SemanticClaim, ...]

    def __post_init__(self):
        validate_model(self)
        if self.kind not in KINDS or self.status not in ("pass", "fail", "unknown"):
            raise ValueError("Invalid evaluated semantic judgment.")
        require_text(self.reason, "semantic evaluation reason")


@dataclass(frozen=True)
class SemanticEvaluation(JsonContract):
    request: SemanticRequest | None
    request_fingerprint: str | None
    policy: SemanticPolicy
    state: str
    engines: tuple[EngineVersion, ...]
    model: EngineVersion | None
    claims: tuple[EvaluatedSemanticClaim, ...]
    findings: tuple[Finding, ...]
    raw_response_sha256: str | None
    raw_response_json: str | None
    error_code: str
    error_message: str
    elapsed_seconds: float
    metadata: SemanticAnalyzerMetadata | None = None
    schema_version: int = 1

    def __post_init__(self):
        validate_model(self)
        require_version(self.schema_version)
        if self.state not in ("complete", "unavailable", "invalid_request", "malformed_response", "model_mismatch",
                              "stale_response", "insufficient_evidence", "timed_out", "cancelled", "service_error"):
            raise ValueError("Unsupported semantic evaluation state.")
        if self.request_fingerprint is not None:
            require_sha256(self.request_fingerprint)
        if self.request is not None and self.request_fingerprint != self.request.dependency_fingerprint:
            raise ValueError("Semantic evaluation must retain its exact request snapshot.")
        if self.raw_response_sha256 is not None:
            require_sha256(self.raw_response_sha256)
        if ((self.raw_response_json is None) != (self.raw_response_sha256 is None) or
                self.raw_response_json is not None and hashlib.sha256(self.raw_response_json.encode()).hexdigest() != self.raw_response_sha256):
            raise ValueError("Raw semantic response hash does not match its preserved JSON.")
        if len(self.error_message) > 512 or len(self.error_code) > 128 or self.elapsed_seconds < 0:
            raise ValueError("Semantic error/time metadata exceeds its profile.")
        unique(tuple(engine.engine_id for engine in self.engines), "semantic engine IDs")
        if self.model is not None and self.model not in self.engines:
            raise ValueError("The semantic model must appear in the evidence engine versions.")
        if self.metadata is not None and (self.model != self.metadata.model or self.metadata.analyzer not in self.engines):
            raise ValueError("Preserved semantic metadata must bind the recorded adapter and model.")

    @property
    def qualification_evidence(self):
        return self.metadata.qualification_evidence if self.metadata is not None else None

    @property
    def qualification_kinds(self):
        return self.metadata.qualification_kinds if self.metadata is not None else ()

    @property
    def dependency_fingerprint(self):
        return fingerprint(dict(request_fingerprint=self.request_fingerprint, policy=self.policy.to_dict(),
                                engines=[engine.to_dict() for engine in self.engines],
                                metadata=self.metadata.to_dict() if self.metadata is not None else None))
