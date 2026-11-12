"""Optional semantic judgments, constrained by current visual evidence.

The injected host port must honor cancellation and timeouts. An arbitrary Python
callback cannot be forcibly interrupted here; late responses are retained but
never promoted to a supported judgment. No provider SDK or paid call is built in.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Callable, Protocol

from ..diagnostic_contracts import ArtifactReference, Evidence, Finding, Judgment, Measurement, ProposedAction
from ..diagnostic_contracts.codec import canonical_json
from .semantic_models import (
    KINDS, SEMANTIC_ENGINE, EvaluatedSemanticClaim, SemanticAnalyzerMetadata, SemanticClaim,
    SemanticEvaluation, SemanticImageSnapshot, SemanticPolicy, SemanticRegionPair,
    SemanticRequest, SemanticResponse, make_semantic_image,
)


class VisionAnalyzer(Protocol):
    def metadata(self) -> SemanticAnalyzerMetadata | dict:
        """Static adapter/model identity; do not perform inference during metadata lookup."""
        ...

    def analyze(self, request: SemanticRequest, *, timeout_seconds: float,
                cancel: Callable[[], bool] | None = None) -> SemanticResponse | dict:
        """Consume only the immutable snapshots and honor the remaining deadline."""
        ...


class SemanticAnalyzerUnavailable(RuntimeError):
    """Host adapter reports temporary absence without importing a provider SDK."""


def _bounded_json(value, max_bytes, max_nodes):
    count = 0
    def visit(item, depth):
        nonlocal count
        count += 1
        if count > max_nodes or depth > 40:
            raise ValueError("Semantic JSON exceeds the bounded structure profile.")
        kind = type(item)
        if kind is str:
            if len(item) > max_bytes:
                raise ValueError("Semantic JSON text exceeds the byte profile.")
        elif item is None or kind in (int, bool):
            pass
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError("Semantic JSON requires finite numbers.")
        elif kind is list:
            for child in item:
                visit(child, depth + 1)
        elif kind is dict and all(type(key) is str for key in item):
            for child in item.values():
                visit(child, depth + 1)
        else:
            raise ValueError("Semantic transport contains a non-JSON value.")
    visit(value, 0)
    encoded = canonical_json(value).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("Semantic JSON exceeds the encoded byte budget.")
    return encoded.decode("utf-8")


def _region_support(region, image, policy):
    if region.bounds is None:
        return "A semantic region has no explicit source-image bounds."
    left, bottom, right, top = region.bounds
    xs = sum(left <= (x/(image.width-1) if image.width > 1 else .5) <= right for x in range(image.width))
    ys = sum(bottom <= (y/(image.height-1) if image.height > 1 else .5) <= top for y in range(image.height))
    if min(xs, ys) < policy.min_region_extent or xs*ys < policy.min_region_pixels:
        return "The named region is unresolved in the actual derived semantic snapshot."
    return ""


def _pair_issues(request, policy):
    views = {view.view_id: view for view in request.view_set.views}
    images = {image.view_id: image for image in request.images}
    for image in request.images:
        if image.view_id not in views or image.source != views[image.view_id].image:
            raise ValueError("A semantic image does not match the current source revision.")
    canonical = request.view_set.canonical_reference
    issues = {}
    for pair in request.pairs:
        reason = ""
        if pair.target.view_id not in views or pair.reference.view_id not in views:
            reason = "A semantic pair refers to a view outside the current source revision."
        elif pair.target.view_id == pair.reference.view_id:
            reason = "A semantic comparison cannot use the target view itself as its canonical comparator."
        elif canonical is None or not canonical.validated or canonical.validation_evidence is None:
            reason = "No accepted canonical design reference with validation evidence is available."
        elif pair.reference.view_id not in canonical.view_ids:
            reason = "The semantic reference view does not belong to the current accepted canonical reference."
        elif pair.reference_lineage != "accepted":
            reason = "The canonical reference is derived from the target, circular, or has unresolved lineage."
        elif pair.target.view_id not in images or pair.reference.view_id not in images:
            reason = "Actual current image snapshots are missing for this semantic pair."
        elif (pair.target_image_sha256 != images[pair.target.view_id].source.sha256 or
              pair.reference_image_sha256 != images[pair.reference.view_id].source.sha256):
            reason = "Semantic source image hashes are stale for the exact current comparison."
        elif pair.target_visibility != "visible" or pair.reference_visibility != "visible":
            reason = "The target/reference region is hidden or its visibility is unknown."
        elif pair.visible_samples < policy.min_visible_samples:
            reason = "The pair has insufficient visible correspondence evidence for a semantic judgment."
        else:
            reason = (_region_support(pair.target, images[pair.target.view_id], policy) or
                      _region_support(pair.reference, images[pair.reference.view_id], policy))
        if reason:
            issues[pair.pair_id] = reason
    return issues


def _engines(metadata):
    result = {SEMANTIC_ENGINE.engine_id: SEMANTIC_ENGINE}
    if metadata is not None:
        for engine in (metadata.analyzer, metadata.model):
            if engine.engine_id in result and result[engine.engine_id] != engine:
                raise ValueError("Semantic adapter/model identifiers conflict with recorded engine versions.")
            result[engine.engine_id] = engine
    return tuple(result[key] for key in sorted(result))


def _finding(request, pair, kind, evaluated, *, metadata, response_sha, policy, elapsed):
    known = {view.view_id for view in request.view_set.views} if request is not None else set()
    regions = tuple(region for region in (pair.target, pair.reference) if region.view_id in known) if pair else ()
    ids = tuple(sorted({region.view_id for region in regions}))
    token = hashlib.sha256(f"{pair.pair_id if pair else 'unavailable'}:{kind}".encode()).hexdigest()[:20]
    artifacts = []
    if response_sha:
        artifacts.append(Evidence("semantic-response-"+token, "artifact", "Canonical JSON returned by the optional semantic adapter; this records a model judgment, not a geometric measurement.",
            ids, regions, artifact=ArtifactReference("semantic-response", response_sha, "application/json")))
    if pair:
        artifacts.append(Evidence("semantic-visibility-"+token, "observation", "Host-verified source-space correspondence/visibility evidence, not proof of semantic identity.",
            ids, regions, measurements=(Measurement("visible_correspondences", pair.visible_samples, "sample"),),
            artifact=ArtifactReference("semantic-correspondence-"+pair.pair_id, pair.evidence_sha256, "application/x-meshvenn-appearance-evidence")))
    if metadata is not None and metadata.qualification_evidence is not None and kind in metadata.qualification_kinds:
        artifacts.append(Evidence("semantic-qualification-"+token, "artifact",
            "Trusted host declaration of qualification evidence for this exact model/version and semantic kind; this does not calibrate its confidence score.",
            ids, regions, artifact=metadata.qualification_evidence))
    if not artifacts:
        artifacts.append(Evidence("semantic-execution-"+token, "execution", evaluated.reason,
                                  measurements=(Measurement("elapsed_seconds", elapsed, "second"),)))
    judgments = tuple(Judgment(claim.explanation, "model", claim.uncertainty+
        " Model confidence is uncalibrated; this judgment cannot certify geometry, export or physical identity.",
        model=metadata.model, confidence=claim.confidence, confidence_calibrated=False)
        for claim in evaluated.claims) if metadata is not None else ()
    return Finding("semantic-"+token, "appearance.semantic_"+kind, "appearance",
                   "info" if evaluated.status == "pass" else "warning", evaluated.status,
                   evaluated.reason, ids, regions, tuple(artifacts), judgments,
                   () if evaluated.status == "pass" else (ProposedAction("semantic-review-"+token, "review_reference",
                       "Review the visible target/canonical regions and preserve the original sources; no automatic correction is authorized.", ids, regions),),
                   required=policy.required, reason=evaluated.reason if evaluated.status == "unknown" else "")


def analyze_semantics(request: SemanticRequest | dict, *, analyzer: VisionAnalyzer | None = None,
                      timeout_seconds: float = 30.0, cancel: Callable[[], bool] | None = None,
                      policy: SemanticPolicy | None = None) -> SemanticEvaluation:
    """Evaluate optional localized model claims without changing source or quality.

    Malformed/stale/contradictory outputs and inadequate evidence abstain. The
    host port owns real inference and hard isolation where required; elapsed
    timeout checks here cannot interrupt a blocked arbitrary Python callback.
    """
    started = time.monotonic()
    policy = policy or SemanticPolicy()
    parsed, metadata, response = None, None, None
    state, error_code, error_message = "complete", "", ""
    raw_json, raw_sha = None, None
    issues = {}
    phase = "request"
    try:
        if type(request) is SemanticRequest:
            parsed = request
        elif type(request) is dict:
            _bounded_json(request, policy.max_request_bytes, 2_000_000)
            parsed = SemanticRequest.from_dict(request)
        else:
            raise ValueError("A semantic request must be the immutable contract or its strict JSON object.")
        _bounded_json(parsed.to_dict(), policy.max_request_bytes, 2_000_000)
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= policy.max_timeout_seconds:
            raise ValueError("Semantic timeout must be finite, positive and inside the host profile.")
        deadline = started + timeout_seconds
        issues = _pair_issues(parsed, policy)
        if cancel is not None and cancel():
            state, error_code, error_message = "cancelled", "cancelled", "Semantic analysis was cancelled before adapter execution."
        elif not parsed.pairs:
            state, error_code, error_message = "insufficient_evidence", "no_regions", "No bounded source-space region comparisons were supplied."
        elif len(issues) == len(parsed.pairs):
            state, error_code, error_message = "insufficient_evidence", "region_evidence", "No requested region has sufficient accepted, visible and resolved evidence."
        elif analyzer is None:
            state, error_code, error_message = "unavailable", "analyzer_unavailable", "No optional semantic analyzer was supplied by the host."
        else:
            phase = "metadata"
            supplied = analyzer.metadata()
            metadata = supplied if type(supplied) is SemanticAnalyzerMetadata else SemanticAnalyzerMetadata.from_dict(supplied)
            _bounded_json(metadata.to_dict(), 16_384, 1000)
            _engines(metadata)
            if cancel is not None and cancel():
                state, error_code, error_message = "cancelled", "cancelled", "Semantic analysis was cancelled before inference."
            elif time.monotonic() >= deadline:
                state, error_code, error_message = "timed_out", "semantic_timeout", "Semantic metadata/preparation exceeded the declared deadline."
            else:
                phase = "response"
                supplied = analyzer.analyze(parsed, timeout_seconds=deadline-time.monotonic(), cancel=cancel)
                # Preserve bounded returned data even after a cancellation/deadline.
                raw_data = supplied.to_dict() if type(supplied) is SemanticResponse else supplied
                raw_json = _bounded_json(raw_data, policy.max_response_bytes, 50_000)
                raw_sha = hashlib.sha256(raw_json.encode()).hexdigest()
                response = SemanticResponse.from_dict(json.loads(raw_json))
                if response.request_fingerprint != parsed.dependency_fingerprint:
                    state, error_code, error_message = "stale_response", "request_mismatch", "The semantic response belongs to a different source/context/region snapshot."
                    response = None
                elif response.model != metadata.model:
                    state, error_code, error_message = "model_mismatch", "model_mismatch", "The response model/version differs from the declared adapter metadata."
                    response = None
                else:
                    pair_map = {pair.pair_id: pair for pair in parsed.pairs}
                    for claim in response.claims:
                        pair = pair_map.get(claim.pair_id)
                        if pair is None or claim.kind not in parsed.kinds or claim.target != pair.target or claim.reference != pair.reference:
                            raise ValueError("A semantic claim changes or escapes its exact current target/reference region.")
                    if cancel is not None and cancel():
                        state, error_code, error_message = "cancelled", "cancelled", "The adapter returned after cancellation; its raw evidence is preserved without promotion."
                    elif time.monotonic() >= deadline:
                        state, error_code, error_message = "timed_out", "semantic_timeout", "The adapter returned after its deadline; its raw evidence is preserved without promotion."
    except SemanticAnalyzerUnavailable:
        state, error_code, error_message = "unavailable", "analyzer_unavailable", "The injected optional semantic analyzer is currently unavailable."
        response = None
    except TimeoutError:
        state, error_code, error_message = "timed_out", "semantic_timeout", "The injected semantic adapter reported a timeout."
    except InterruptedError:
        state, error_code, error_message = "cancelled", "cancelled", "The injected semantic adapter reported cancellation."
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError) as exc:
        state = "invalid_request" if phase == "request" else "malformed_response"
        error_code, error_message = state, str(exc)[:512] or "Semantic data violates the strict bounded contract."
        response = None
    except Exception as exc:
        state, error_code, error_message = "service_error", "analyzer_error", f"The injected semantic adapter raised {type(exc).__name__}; no inference result was accepted."
        response = None

    elapsed = time.monotonic()-started
    evaluated, findings = [], []
    if parsed is not None and parsed.pairs:
        groups = {}
        if response is not None:
            for claim in response.claims:
                groups.setdefault((claim.pair_id, claim.kind), []).append(claim)
        for pair in parsed.pairs:
            for kind in parsed.kinds:
                claims = tuple(groups.get((pair.pair_id, kind), ()))
                status = "unknown"
                reason = issues.get(pair.pair_id) or error_message
                if not reason:
                    if not claims:
                        reason = "The analyzer supplied no claim for this requested visible region/kind."
                    elif len({claim.verdict for claim in claims}) > 1:
                        reason = "Semantic judgments conflict for the same region; confidence does not choose a winner."
                    elif any(claim.verdict == "unknown" or claim.support != "sufficient" for claim in claims):
                        reason = "The model explicitly abstained or reported insufficient semantic support."
                    elif any(claim.confidence is not None and policy.min_confidence is not None and
                             claim.confidence < policy.min_confidence for claim in claims):
                        reason = "The optional uncalibrated model score is below the declared abstention floor."
                    else:
                        status = "pass" if claims[0].verdict == "consistent" else "fail"
                        reason = ("The optional model reports consistency for this supported visible canonical comparison." if status == "pass" else
                                  "The optional model reports a localized identity/accessory/motif change requiring review.")
                item = EvaluatedSemanticClaim(pair.pair_id, kind, status, reason, claims)
                evaluated.append(item)
                findings.append(_finding(parsed, pair, kind, item, metadata=metadata,
                                         response_sha=raw_sha, policy=policy, elapsed=elapsed))
    else:
        reason = error_message or "No supported semantic region was available."
        item = EvaluatedSemanticClaim("unavailable", "identity", "unknown", reason, ())
        findings.append(_finding(parsed, None, "identity", item, metadata=metadata,
                                 response_sha=raw_sha, policy=policy, elapsed=elapsed))
    try:
        engines = _engines(metadata)
    except ValueError:
        metadata = None
        engines = (SEMANTIC_ENGINE,)
    return SemanticEvaluation(parsed, parsed.dependency_fingerprint if parsed is not None else None,
        policy, state, engines, metadata.model if metadata is not None else None, tuple(evaluated), tuple(findings),
        raw_sha, raw_json, error_code[:128], error_message[:512], elapsed, metadata=metadata)


__all__ = ("VisionAnalyzer", "SemanticAnalyzerUnavailable", "SemanticAnalyzerMetadata", "SemanticImageSnapshot", "make_semantic_image",
           "SemanticRegionPair", "SemanticRequest", "SemanticClaim", "SemanticResponse", "SemanticPolicy",
           "EvaluatedSemanticClaim", "SemanticEvaluation", "analyze_semantics")
