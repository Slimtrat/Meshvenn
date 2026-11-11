"""Deterministic preparation checks for supported orthographic view inputs."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from typing import Mapping, Sequence

from ..diagnostic_contracts import (
    ArtifactReference, DiagnosticPolicy, DiagnosticReport, DiagnosticResolution, EngineVersion,
    Evidence, Finding, Judgment, Measurement, ProposedAction, Threshold,
    ViewSetRevision,
)
from .rasters import MAX_PIXELS, ViewInput
from .registration import (
    AlignmentAnchor, AlignmentProposal, CertifiedProjectionInput, fit_similarity,
    mask_from_input, mask_iou, resample_mask, transform_hash,
)

ENGINE = EngineVersion("meshvenn.preflight", "1.0.0")


@dataclass(frozen=True)
class PreflightPolicy:
    alpha_threshold: float = 0.1
    mask_threshold: float = 0.5
    max_alpha_disagreement: float = 0.02
    min_scale: float = 0.8
    max_scale: float = 1.25
    max_offset: float = 0.15
    healthy_iou: float = 0.98
    min_registered_iou: float = 0.97
    min_improvement: float = 0.05
    required_cameras: tuple[tuple[float, float], ...] = ((0., 0.), (90., 0.), (180., 0.), (270., 0.))

    def __post_init__(self):
        for name in ("alpha_threshold", "mask_threshold", "max_alpha_disagreement",
                     "healthy_iou", "min_registered_iou", "min_improvement"):
            if not math.isfinite(getattr(self, name)) or not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} must be finite in (0,1].")
        if not 0.25 <= self.min_scale <= 1 <= self.max_scale <= 4:
            raise ValueError("Scale policy must contain identity inside ProjectionAlignment bounds.")
        if not math.isfinite(self.max_offset) or not 0 <= self.max_offset <= 0.5:
            raise ValueError("Offset policy must be within ProjectionAlignment bounds.")
        normalized = tuple((float(a) % 360, float(e)) for a, e in self.required_cameras)
        if any(not math.isfinite(a) or not math.isfinite(e) or abs(e) > 90 for a, e in normalized):
            raise ValueError("Required orthographic camera angles must be finite and valid.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Required camera directions must be unique.")
        object.__setattr__(self, "required_cameras", normalized)

    def contract(self) -> DiagnosticPolicy:
        digest = hashlib.sha256(json.dumps(asdict(self), sort_keys=True, allow_nan=False).encode()).hexdigest()
        return DiagnosticPolicy("meshvenn.preflight", "1.0.0", digest,
                                required_checks=("input.integrity", "coverage.insufficient"))


@dataclass(frozen=True)
class PreflightResult:
    report: DiagnosticReport
    proposals: tuple[AlignmentProposal, ...]


def _camera_supported(view) -> bool:
    camera = view.camera
    return (camera.projection == "orthographic" and camera.verified and
            camera.verification_evidence is not None and
            camera.azimuth_degrees is not None and camera.elevation_degrees is not None)


def _camera_key(view):
    return (round(view.camera.azimuth_degrees % 360, 6), round(view.camera.elevation_degrees, 6), view.camera.flip_x)


def _assumptions(anchors: Sequence[AlignmentAnchor]) -> tuple[str, ...]:
    return ("Orthographic camera declarations require independent verification evidence.",
            "Image and mask adapters preserve original content; no cross-view truth attribution.",
            "Similarity checks do not certify identity, semantic parts or camera calibration.") + tuple(
                f"anchor:{a.target_view_id}:{a.reference_view_id}:{a.evidence_sha256}"
                for a in sorted(anchors, key=lambda a: (a.target_view_id, a.reference_view_id)))


def analyze_preflight(view_set: ViewSetRevision, inputs: Mapping[str, ViewInput], *,
                      anchors: Sequence[AlignmentAnchor] = (),
                      policy: PreflightPolicy | None = None) -> PreflightResult:
    """Read-only analysis. Missing/unsupported data yield findings, never success.

    ``inputs`` is a host-decoded or PNG-adapted buffer map keyed by immutable view
    IDs. Metadata hashes/dimensions are checked against the actual source before
    measurements or registration. ``anchors`` must be validated canonical views
    at the exact same verified camera, not provisional reconstruction outputs.
    """
    policy = policy or PreflightPolicy()
    anchors = tuple(anchors)
    if len({a.target_view_id for a in anchors}) != len(anchors):
        raise ValueError("At most one independent alignment anchor per target is allowed.")
    views = {v.view_id: v for v in view_set.views}
    if any(a.target_view_id not in views or a.reference_view_id not in views for a in anchors):
        raise ValueError("Every alignment anchor must refer to this exact view set.")
    findings, valid, masks, proposals = [], {}, {}, []

    def finding(code, category, status, message, ids=(), *, severity="error",
                measurements=(), action="inspect_input", reason="", key="", required=True,
                interpretation=""):
        ids = tuple(ids)
        token = f"{code}:{','.join(ids)}:{key}"
        identifier = hashlib.sha256(token.encode()).hexdigest()[:20]
        artifact = None
        if category == "camera" and ids:
            artifact = views[ids[0]].camera.verification_evidence
        elif ids and ids[0] in inputs:
            source = inputs[ids[0]].mask if key == "mask" else inputs[ids[0]].image
            if source and len(source.source_sha256) == 64:
                artifact = ArtifactReference(f"source-{identifier}", source.source_sha256, source.media_type)
        if not measurements and artifact is None:
            measurements = (Measurement("available_verified_evidence", 0, "count"),)
        evidence = (Evidence(f"e-{identifier}", "observation", message, ids,
                             measurements=tuple(measurements), artifact=artifact),)
        actions = () if status == "pass" else (ProposedAction(f"a-{identifier}", action, message, ids),)
        interpretations = () if not interpretation else (
            Judgment(interpretation, "inference", "This check does not establish cross-view geometric truth."),)
        findings.append(Finding(f"f-{identifier}", code, category, severity if status != "pass" else "info",
                                status, message, ids, evidence=evidence, interpretations=interpretations,
                                proposed_actions=actions, required=required,
                                reason=reason or (message if status in ("unknown", "not_applicable") else "")))

    for view_id, view in sorted(views.items()):
        data = inputs.get(view_id)
        if data is None:
            finding("input.missing", "input", "unknown", "Provide the original color image and mask for this view.", (view_id,), reason="No source buffer was supplied.")
            valid[view_id] = False
            continue
        okay = True
        for label, raster, reference in (("image", data.image, view.image), ("mask", data.mask, view.mask)):
            if raster is None and reference is None and label == "mask":
                continue
            if raster is not None and raster.error:
                code = "input.unsupported_format" if raster.unsupported else "input.unreadable"
                finding(code, "input", "unknown" if raster.unsupported else "fail", f"{label}: {raster.error}", (view_id,), key=label)
                okay = False
                continue
            if raster is None or reference is None:
                finding("input.missing", "input", "unknown", f"{label}: source and declared content reference are both required.", (view_id,), key=label)
                okay = False
                continue
            if reference.sha256 != raster.source_sha256:
                finding("input.hash_mismatch", "input", "fail", f"{label}: original source bytes do not match this view revision; select or reload the correct source.", (view_id,), key=label)
                okay = False
            width, height = raster.width, raster.height
            if (not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0 or
                    width * height > MAX_PIXELS or len(raster.rgba) != width * height * 4 or
                    (width, height) != (reference.width, reference.height)):
                finding("input.dimension_mismatch", "input", "fail", f"{label}: decoded dimensions or buffer length do not match the declared source; re-export the complete image.", (view_id,), key=label)
                okay = False
            elif any(not math.isfinite(value) for value in raster.rgba):
                finding("input.nonfinite", "input", "fail", f"{label}: pixels contain NaN or infinity; re-export a finite image.", (view_id,), key=label)
                okay = False
            elif any(not 0 <= value <= 1 for value in raster.rgba):
                finding("input.value_range", "input", "fail", f"{label}: normalized RGBA values fall outside [0,1]; check the decoder and alpha encoding.", (view_id,), key=label)
                okay = False
        if okay and data.mask and (data.mask.width, data.mask.height) != (data.image.width, data.image.height):
            finding("input.dimension_mismatch", "input", "fail", "Color image and mask dimensions differ; prepare them on an identical grid.", (view_id,), key="pair")
            okay = False
        valid[view_id] = okay
        if not okay:
            continue
        finding("input.integrity", "input", "pass", "Original source hashes, dimensions and finite normalized RGBA buffers match this revision.", (view_id,), measurements=(Measurement("width", data.image.width, "pixel"), Measurement("height", data.image.height, "pixel")))
        mask = masks[view_id] = mask_from_input(data, policy.alpha_threshold, policy.mask_threshold)
        count = mask.occupied_count
        alpha = bytes(int(data.image.rgba[i] >= policy.alpha_threshold) for i in range(3, len(data.image.rgba), 4))
        alpha_count = sum(alpha)
        if not alpha_count:
            finding("input.empty_alpha", "input", "fail", "The color image is fully transparent; restore visible subject pixels.", (view_id,), measurements=(Measurement("alpha_occupied", 0, "pixel", Threshold(">", 0, "pixel")),))
            valid[view_id] = False
        else:
            finding("input.alpha_occupancy", "input", "pass", "The original color alpha contains visible pixels.", (view_id,),
                    measurements=(Measurement("alpha_occupied", alpha_count, "pixel", Threshold(">", 0, "pixel")),
                                  Measurement("alpha_occupied_fraction", alpha_count / len(alpha), "fraction")))
        if not data.mask and alpha_count == len(alpha):
            finding("input.segmentation_missing", "input", "unknown", "The color image is fully opaque and has no subject mask; provide segmentation before measuring framing.", (view_id,), action="repair_mask")
            valid[view_id] = False
            continue
        if not count:
            finding("input.empty_mask", "input", "fail", "No occupied subject pixels remain; inspect the mask and its alpha before reconstruction.", (view_id,), action="repair_mask", measurements=(Measurement("occupied", 0, "pixel", Threshold(">", 0, "pixel")),))
            valid[view_id] = False
        else:
            finding("input.mask_occupancy", "input", "pass", "The subject mask contains occupied pixels.", (view_id,),
                    measurements=(Measurement("occupied", count, "pixel", Threshold(">", 0, "pixel")),
                                  Measurement("occupied_fraction", count / len(mask.values), "fraction")))
            boundary = sum(bool(mask.values[y * mask.width + x]) for y in range(mask.height) for x in range(mask.width)
                           if x in (0, mask.width - 1) or y in (0, mask.height - 1))
            if boundary:
                finding("input.subject_truncated", "input", "fail", "Subject pixels touch the image boundary; verify the original framing and restore any cut-off part.", (view_id,), measurements=(Measurement("boundary_occupied", boundary, "pixel", Threshold("==", 0, "pixel")),), interpretation="Boundary contact is a truncation risk; it does not prove which part extends outside the image.")
                valid[view_id] = False
            else:
                finding("input.framing", "input", "pass", "No occupied subject pixels touch the image boundary.", (view_id,),
                        measurements=(Measurement("boundary_occupied", 0, "pixel", Threshold("==", 0, "pixel")),))
            if data.mask and 0 < alpha_count < len(alpha):
                union = sum(bool(a) or bool(b) for a, b in zip(alpha, mask.values))
                disagreement = sum(bool(a) != bool(b) for a, b in zip(alpha, mask.values)) / union if union else 0
                if disagreement > policy.max_alpha_disagreement:
                    finding("input.alpha_mask_mismatch", "input", "fail", "Color alpha and subject mask disagree; inspect their shared crop and segmentation.", (view_id,), action="repair_mask", measurements=(Measurement("alpha_mask_disagreement", disagreement, "fraction", Threshold("<=", policy.max_alpha_disagreement, "fraction")),))
                    valid[view_id] = False

    for view_id, view in sorted(views.items()):
        if view.camera.projection == "perspective":
            finding("camera.unsupported", "camera", "fail", "Perspective is unsupported by the orthographic preparation path; provide a verified orthographic view.", (view_id,), action="verify_camera")
        elif not _camera_supported(view):
            finding("camera.unverified", "camera", "unknown", "Camera declaration lacks independent orthographic verification; a generated view label is not calibration evidence.", (view_id,), action="verify_camera")
        else:
            finding("camera.support", "camera", "pass", "The declared orthographic camera has verification evidence and is supported by projection math.", (view_id,))

    available = {_camera_key(v)[:2] for v in views.values() if v.role == "observation" and
                 _camera_supported(v) and valid.get(v.view_id)}
    missing = tuple(camera for camera in policy.required_cameras if camera not in available)
    finding("coverage.insufficient", "coverage", "fail" if missing else "pass",
            "Provide usable verified observations at directions: " + ", ".join(f"{a:g}/{e:g} degrees" for a, e in missing) if missing else "All required camera directions have usable verified observations.",
            measurements=(Measurement("missing_directions", len(missing), "view", Threshold("==", 0, "view")),), action="provide_view")

    groups = defaultdict(list)
    for view_id, view in sorted(views.items()):
        if valid.get(view_id) and view.role == "observation":
            groups[inputs[view_id].image.source_sha256].append(view_id)
    for ids in groups.values():
        known = [_camera_key(views[v]) for v in ids if _camera_supported(views[v])]
        if len(set(known)) > 1:
            finding("input.duplicate", "input", "unknown", "Identical original color bytes are assigned to different cameras; confirm duplication or intentional visual symmetry.", ids, severity="warning", required=False,
                    measurements=(Measurement("identical_source_views", len(ids), "view"), Measurement("distinct_cameras", len(set(known)), "camera")))

    assumptions = _assumptions(anchors) + tuple(
        f"decoded:{view_id}:{data.image.decoded_sha256}:{data.mask.decoded_sha256 if data.mask else 'none'}"
        for view_id, data in sorted(inputs.items()) if view_id in views)
    anchor_map = {a.target_view_id: a for a in anchors}
    proposal_data = []
    for view_id, view in sorted(views.items()):
        if view.role != "observation":
            continue
        anchor = anchor_map.get(view_id)
        canonical = view_set.canonical_reference
        if not valid.get(view_id) or not _camera_supported(view):
            finding("alignment.checked", "alignment", "unknown", "Resolve preparation and camera findings before registration.", (view_id,), action="inspect_input")
            continue
        if (anchor is None or canonical is None or not canonical.validated or canonical.validation_evidence is None or
                anchor.reference_view_id not in canonical.view_ids):
            finding("alignment.reference_missing", "alignment", "unknown", "Select an independently validated canonical same-camera reference before proposing alignment.", (view_id,), action="select_reference")
            continue
        ref_id = anchor.reference_view_id
        reference = views[ref_id]
        if (not valid.get(ref_id) or not _camera_supported(reference) or
                _camera_key(view) != _camera_key(reference) or
                reference.role != "reference"):
            finding("alignment.reference_missing", "alignment", "unknown", "The selected reference lacks usable independent evidence at the same verified camera.", (view_id, ref_id), action="review_reference")
            continue
        if not view.alignment.is_identity or not reference.alignment.is_identity:
            finding("alignment.checked", "alignment", "unknown", "This revision already contains alignment; analyze immutable unaligned originals to avoid accumulating corrections.", (view_id,), action="review_reference")
            continue
        source_mask, reference_mask = masks[view_id], masks[ref_id]
        target = resample_mask(reference_mask, source_mask.width, source_mask.height)
        before = mask_iou(source_mask, target)
        if before >= policy.healthy_iou:
            finding("alignment.within_tolerance", "alignment", "pass", "Framing agrees with the independent reference; retain the original unchanged.", (view_id, ref_id), measurements=(Measurement("mask_iou", before, "fraction", Threshold(">=", policy.healthy_iou, "fraction")),))
            continue
        fit = fit_similarity(source_mask, reference_mask, min_scale=policy.min_scale,
                             max_scale=policy.max_scale, max_offset=policy.max_offset)
        if fit is None or fit[2] < policy.min_registered_iou or fit[2] - before < policy.min_improvement:
            after = fit[2] if fit else before
            finding("alignment.shape_mismatch", "alignment", "unknown", "Bounded uniform registration cannot establish a sufficient match; review the reference or shape rather than stretching proportions.", (view_id, ref_id), action="review_reference", measurements=(Measurement("before_iou", before, "fraction"), Measurement("best_bounded_iou", after, "fraction", Threshold(">=", policy.min_registered_iou, "fraction"))), interpretation="Residual shape differences or insufficient evidence remain; this does not attribute a cross-view conflict.")
            continue
        alignment, before, after = fit
        finding("alignment.suspected", "alignment", "fail", "A bounded uniform scale/offset improves agreement with the independent reference; review the before/after proposal.", (view_id, ref_id), action="apply_alignment", measurements=(Measurement("before_iou", before, "fraction"), Measurement("after_iou", after, "fraction", Threshold(">=", policy.min_registered_iou, "fraction")), Measurement("improvement", after-before, "fraction", Threshold(">=", policy.min_improvement, "fraction")), Measurement("scale", alignment.scale, "ratio"), Measurement("offset_u", alignment.offset_u, "image_width"), Measurement("offset_v", alignment.offset_v, "image_height")))
        proposal_data.append((view_id, ref_id, anchor, alignment, before, after))

    findings.sort(key=lambda f: (f.code, f.view_ids, f.finding_id))
    dimensions = [(r.image.width, r.image.height) for r in inputs.values() if r.image.width and r.image.height]
    resolution = DiagnosticResolution(max((w for w, _ in dimensions), default=1), max((h for _, h in dimensions), default=1))
    report = DiagnosticReport("preflight-" + view_set.dependency_fingerprint[:20], view_set,
                              (ENGINE,), policy.contract(), resolution, tuple(findings), assumptions)
    report = replace(report, report_id="preflight-" + report.dependency_fingerprint[:20])
    for view_id, ref_id, anchor, alignment, before, after in proposal_data:
        source, reference = inputs[view_id], inputs[ref_id]
        dependencies = (report.dependency_fingerprint, source.image.source_sha256,
                        source.mask.source_sha256 if source.mask else None,
                        reference.image.source_sha256, reference.mask.source_sha256 if reference.mask else None,
                        anchor.evidence_sha256)
        certificate = transform_hash(alignment, *dependencies)
        proposals.append(AlignmentProposal("alignment-" + certificate[:20], view_id, ref_id, alignment,
                                          before, after, *dependencies, certificate))
    return PreflightResult(report, tuple(proposals))


def accept_alignment(proposal: AlignmentProposal, result: PreflightResult, view_set: ViewSetRevision,
                     inputs: Mapping[str, ViewInput], *, anchors: Sequence[AlignmentAnchor],
                     policy: PreflightPolicy | None = None) -> CertifiedProjectionInput:
    """Accept only an unchanged, reproduced proposal and bind both consumers.

    Reanalysis detects stale metadata, mutated buffers, policy/anchor changes and
    caller-forged transforms. Acceptance creates a derived input, never edits a
    source file or changes a ViewRevision silently.
    """
    if proposal not in result.proposals:
        raise ValueError("Proposal does not belong to this preflight result.")
    current = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
    if current.report.dependency_fingerprint != result.report.dependency_fingerprint or proposal not in current.proposals:
        raise ValueError("Alignment proposal is stale or its source/evidence/transform changed.")
    policy = policy or PreflightPolicy()
    source = inputs[proposal.view_id]
    original = mask_from_input(source, policy.alpha_threshold, policy.mask_threshold)
    return CertifiedProjectionInput(source, proposal.alignment.align_mask(original), proposal.alignment,
                                    proposal.transform_sha256, proposal.source_image_sha256,
                                    proposal.source_mask_sha256)
