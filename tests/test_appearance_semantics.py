"""Adapter-contract fixtures only: no real model identity quality is qualified."""
from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from core.appearance_diagnostics.semantics import (
    SemanticAnalyzerMetadata, SemanticAnalyzerUnavailable, SemanticClaim, SemanticEvaluation, SemanticImageSnapshot,
    SemanticPolicy, SemanticRegionPair, SemanticRequest, SemanticResponse, analyze_semantics, make_semantic_image,
)
from core.diagnostic_contracts import (
    ArtifactReference, CameraDeclaration, CanonicalReference, DiagnosticPolicy, DiagnosticReport,
    DiagnosticResolution, EngineVersion, Evidence, Finding, Measurement, Region, ViewRevision, ViewSetRevision,
)
from core.diagnostics_preflight import RasterInput


def request_fixture():
    proof = ArtifactReference("fixture-camera", "a"*64, "application/json")
    camera = CameraDeclaration("orthographic", 0, 0, verified=True, verification_evidence=proof)
    images, views = [], []
    for name in ("reference", "target"):
        raster = RasterInput.from_pixels(16, 16, (.2, .3, .4, 1.)*256, source_bytes=("semantic-fixture-"+name).encode())
        view = ViewRevision(name, 1, raster.content_reference(), None, camera,
                            role="reference" if name == "reference" else "observation")
        views.append(view)
        images.append(make_semantic_image(view_id=name, source=view.image,
            original_decoded_sha256=raster.decoded_sha256, source_width=16, source_height=16,
            width=16, height=16, rgba=raster.rgba))
    # A candidate derived from an accepted design baseline is legitimate D4 input.
    views[1] = replace(views[1], origin="derived", derived_from=(views[0].image.sha256,))
    canonical = CanonicalReference("accepted-design", 1, views[0].image, validated=True,
        view_ids=("reference",), validation_evidence=ArtifactReference("accepted-proof", "b"*64, "application/json"))
    revision = ViewSetRevision("semantic-fixture-not-model-qualification", 1, tuple(views), canonical)
    pair = SemanticRegionPair("identity-region", Region("target", "identity", (.1, .1, .9, .9)),
        Region("reference", "identity", (.1, .1, .9, .9)), views[1].image.sha256, views[0].image.sha256,
        "visible", "visible", "c"*64, "accepted", visible_samples=144)
    return SemanticRequest(revision, "d"*64, (pair,), tuple(images))


class FixtureAnalyzer:
    """A fake port testing orchestration, never a qualified vision inference."""
    def __init__(self, transform=None):
        self.transform = transform
        self.calls = []
        self.model = EngineVersion("test.semantic_model", "unqualified-adapter-fixture")
        self.adapter = EngineVersion("test.semantic_adapter", "fixture-only-1")

    def metadata(self):
        return SemanticAnalyzerMetadata(self.adapter, self.model)

    def analyze(self, request, *, timeout_seconds, cancel=None):
        self.calls.append((request, timeout_seconds, cancel))
        claims = tuple(SemanticClaim(f"{pair.pair_id}-{kind}", pair.pair_id, kind, "consistent",
            pair.target, pair.reference, "Fixture response for adapter validation only.",
            "No real semantic model was executed.", confidence=.8) for pair in request.pairs for kind in request.kinds)
        response = SemanticResponse(request.dependency_fingerprint, self.model, claims)
        return self.transform(response, request) if self.transform else response


class SemanticContractTests(unittest.TestCase):
    def test_snapshots_are_strict_derived_source_space_and_hash_bound(self):
        request = request_fixture()
        snapshot = request.images[0]
        self.assertNotEqual(snapshot.sha256, snapshot.source.sha256)
        self.assertEqual(SemanticImageSnapshot.from_json(snapshot.to_json()), snapshot)
        self.assertEqual(snapshot.coordinate_space, "source")
        with self.assertRaises(ValueError):
            replace(snapshot, rgba=(.1, .3, .4, 1.)*256)
        with self.assertRaises(ValueError):
            replace(snapshot, coordinate_space="aligned")
        with self.assertRaises(ValueError):
            replace(snapshot, color_space="unspecified")
        with self.assertRaises(ValueError):
            replace(snapshot, width=129)
        with self.assertRaises(ValueError):
            replace(snapshot, rgba=(True, .3, .4, 1.)*256)

    def test_request_fingerprint_binds_images_visibility_canonical_and_context_not_order(self):
        request = request_fixture()
        self.assertEqual(SemanticRequest.from_json(request.to_json()), request)
        reversed_views = replace(request.view_set, input_order=tuple(reversed(request.view_set.input_order)))
        self.assertEqual(request.dependency_fingerprint, replace(request, view_set=reversed_views).dependency_fingerprint)
        for changed in (replace(request, context_sha256="e"*64),
                        replace(request, pairs=(replace(request.pairs[0], target_visibility="hidden"),)),
                        replace(request, view_set=replace(request.view_set,
                            canonical_reference=replace(request.view_set.canonical_reference, revision=2)))):
            self.assertNotEqual(request.dependency_fingerprint, changed.dependency_fingerprint)
        original = request.images[0]
        changed_image = make_semantic_image(view_id=original.view_id, source=original.source,
            original_decoded_sha256=original.original_decoded_sha256, source_width=16, source_height=16,
            width=16, height=16, rgba=(.5, .3, .4, 1.)*256)
        self.assertNotEqual(request.dependency_fingerprint,
                            replace(request, images=(changed_image, request.images[1])).dependency_fingerprint)

    def test_json_rejects_versions_unknown_calibration_fields_and_callables(self):
        request = request_fixture()
        data = request.to_dict()
        data["schema_version"] = 2
        with self.assertRaises(ValueError):
            SemanticRequest.from_dict(data)
        invalid = request.to_dict()
        invalid["analyzer"] = lambda: None
        evaluation = analyze_semantics(invalid)
        self.assertEqual(evaluation.state, "invalid_request")
        self.assertTrue(all(f.status == "unknown" for f in evaluation.findings))
        analyzer = FixtureAnalyzer(lambda response, _: {**response.to_dict(), "confidence_calibrated": True})
        evaluation = analyze_semantics(request, analyzer=analyzer)
        self.assertEqual(evaluation.state, "malformed_response")
        self.assertIsNotNone(evaluation.raw_response_sha256)
        self.assertTrue(all(f.status == "unknown" for f in evaluation.findings))

    def test_absent_analyzer_explicit_unknown_has_no_invented_model(self):
        evaluation = analyze_semantics(request_fixture())
        self.assertEqual(evaluation.state, "unavailable")
        self.assertIsNone(evaluation.model)
        self.assertIsNone(evaluation.raw_response_sha256)
        self.assertTrue(all(f.status == "unknown" and f.reason for f in evaluation.findings))
        self.assertEqual(SemanticEvaluation.from_json(evaluation.to_json()), evaluation)

    def test_fixture_port_preserves_model_and_uncalibrated_judgments(self):
        request, analyzer = request_fixture(), FixtureAnalyzer()
        evaluation = analyze_semantics(request, analyzer=analyzer)
        self.assertEqual(evaluation.state, "complete")
        self.assertTrue(all(item.status == "pass" for item in evaluation.claims))
        self.assertEqual(evaluation.model, analyzer.model)
        self.assertIn(analyzer.model, evaluation.engines)
        self.assertIn(analyzer.adapter, evaluation.engines)
        snapshot_hashes = {image.sha256 for image in request.images}
        self.assertTrue(snapshot_hashes <= {e.artifact.sha256 for f in evaluation.findings for e in f.evidence if e.artifact})
        self.assertEqual(evaluation.raw_response_sha256, hashlib.sha256(evaluation.raw_response_json.encode()).hexdigest())
        self.assertTrue(all(j.kind == "model" and not j.confidence_calibrated and j.calibration_evidence is None
                            for f in evaluation.findings for j in f.interpretations))
        self.assertTrue(all(not f.required for f in evaluation.findings))
        self.assertGreater(analyzer.calls[0][1], 0)
        self.assertLessEqual(analyzer.calls[0][1], 30)
        self.assertEqual(SemanticEvaluation.from_json(evaluation.to_json()), evaluation)
        self.assertIsNone(evaluation.qualification_evidence)
        self.assertEqual(evaluation.qualification_kinds, ())

    def test_host_qualification_record_is_model_bound_and_never_model_response_data(self):
        request = request_fixture()
        unqualified = analyze_semantics(request, analyzer=FixtureAnalyzer())
        class DeclaredQualification(FixtureAnalyzer):
            def metadata(self):
                return SemanticAnalyzerMetadata(self.adapter, self.model,
                    qualification_evidence=ArtifactReference("fixture-qualified-declaration-only", "e"*64, "application/json"),
                    qualification_kinds=("identity",))
        qualified = analyze_semantics(request, analyzer=DeclaredQualification())
        self.assertEqual(qualified.qualification_kinds, ("identity",))
        self.assertEqual(qualified.qualification_evidence.sha256, "e"*64)
        self.assertNotEqual(unqualified.dependency_fingerprint, qualified.dependency_fingerprint)
        self.assertTrue(any(e.artifact == qualified.qualification_evidence
                            for f in qualified.findings if f.code == "appearance.semantic_identity" for e in f.evidence))
        self.assertTrue(all(not j.confidence_calibrated for f in qualified.findings for j in f.interpretations))
        self.assertEqual(SemanticEvaluation.from_json(qualified.to_json()), qualified)
        injected = FixtureAnalyzer(lambda response, _: {**response.to_dict(),
            "qualification_evidence": {"artifact_id": "self-qualify", "sha256": "f"*64, "media_type": "application/json"}})
        rejected = analyze_semantics(request, analyzer=injected)
        self.assertEqual(rejected.state, "malformed_response")
        self.assertIsNone(rejected.qualification_evidence)
        with self.assertRaises(ValueError):
            SemanticAnalyzerMetadata(FixtureAnalyzer().adapter, FixtureAnalyzer().model, qualification_kinds=("identity",))

    def test_changed_claim_is_localized_review_only_and_no_auto_correction(self):
        analyzer = FixtureAnalyzer(lambda response, _: replace(response,
            claims=tuple(replace(claim, verdict="changed") for claim in response.claims)))
        request = request_fixture()
        evaluation = analyze_semantics(request, analyzer=analyzer)
        self.assertTrue(all(f.status == "fail" and request.pairs[0].target in f.regions for f in evaluation.findings))
        self.assertTrue(all(a.kind == "review_reference" for f in evaluation.findings for a in f.proposed_actions))

    def test_contradictory_judgments_abstain_without_picking_high_confidence(self):
        def conflict(response, _):
            duplicate = replace(response.claims[0], claim_id="contradiction", verdict="changed", confidence=.999)
            return replace(response, claims=response.claims+(duplicate,))
        evaluation = analyze_semantics(request_fixture(), analyzer=FixtureAnalyzer(conflict))
        item = next(item for item in evaluation.claims if item.kind == "accessory")
        self.assertEqual(item.status, "unknown")
        self.assertIn("conflict", item.reason)
        self.assertEqual(len(item.claims), 2)

    def test_low_support_low_score_and_omitted_kinds_are_unknown(self):
        for transform in (
            lambda response, _: replace(response, claims=tuple(replace(c, support="limited") for c in response.claims)),
            lambda response, _: replace(response, claims=tuple(replace(c, confidence=.1) for c in response.claims)),
            lambda response, _: replace(response, claims=()),
        ):
            with self.subTest(transform=transform):
                result = analyze_semantics(request_fixture(), analyzer=FixtureAnalyzer(transform))
                self.assertTrue(all(item.status == "unknown" for item in result.claims))

    def test_confidence_is_optional_and_abstention_policy_changes_dependencies(self):
        analyzer = FixtureAnalyzer(lambda response, _: replace(response, claims=tuple(replace(c, confidence=None) for c in response.claims)))
        evaluation = analyze_semantics(request_fixture(), analyzer=analyzer)
        self.assertTrue(all(item.status == "pass" for item in evaluation.claims))
        normal = analyze_semantics(request_fixture(), analyzer=FixtureAnalyzer())
        strict = analyze_semantics(request_fixture(), analyzer=FixtureAnalyzer(), policy=SemanticPolicy(min_confidence=.9))
        self.assertNotEqual(normal.dependency_fingerprint, strict.dependency_fingerprint)
        self.assertTrue(all(item.status == "unknown" for item in strict.claims))

    def test_hidden_or_unknown_regions_never_receive_supported_judgments(self):
        request = request_fixture()
        hidden = replace(request.pairs[0], pair_id="hidden", target_visibility="hidden")
        request = replace(request, pairs=request.pairs+(hidden,))
        evaluation = analyze_semantics(request, analyzer=FixtureAnalyzer())
        hidden_results = [item for item in evaluation.claims if item.pair_id == "hidden"]
        self.assertTrue(all(item.status == "unknown" and "hidden" in item.reason for item in hidden_results))
        self.assertTrue(all(item.status == "pass" for item in evaluation.claims if item.pair_id != "hidden"))
        for visibility in ("hidden", "unknown"):
            analyzer = FixtureAnalyzer()
            result = analyze_semantics(replace(request, pairs=(replace(hidden, target_visibility=visibility),)), analyzer=analyzer)
            self.assertEqual(analyzer.calls, [])
            self.assertEqual(result.state, "insufficient_evidence")

    def test_low_visibility_or_unresolved_snapshot_region_avoids_analyzer(self):
        request = request_fixture()
        for pair in (replace(request.pairs[0], visible_samples=1),
                     replace(request.pairs[0], target=Region("target", "tiny-important-part", (.1, .1, .11, .11)))):
            analyzer = FixtureAnalyzer()
            result = analyze_semantics(replace(request, pairs=(pair,)), analyzer=analyzer)
            self.assertEqual(result.state, "insufficient_evidence")
            self.assertEqual(analyzer.calls, [])
            self.assertTrue(all(item.status == "unknown" for item in result.claims))

    def test_self_comparison_abstains_without_invalid_duplicate_d1_regions(self):
        request = request_fixture()
        pair = request.pairs[0]
        self_pair = replace(pair, target=pair.reference, target_image_sha256=pair.reference_image_sha256)
        analyzer = FixtureAnalyzer()
        result = analyze_semantics(replace(request, pairs=(self_pair,)), analyzer=analyzer)
        self.assertEqual(result.state, "insufficient_evidence")
        self.assertEqual(analyzer.calls, [])
        self.assertTrue(all(f.status == "unknown" for f in result.findings))
        self.assertEqual(SemanticEvaluation.from_json(result.to_json()), result)

    def test_accepted_design_ancestor_allowed_target_derived_or_circular_abstains(self):
        request = request_fixture()
        self.assertEqual(request.view_set.views[1].derived_from, (request.view_set.views[0].image.sha256,))
        self.assertTrue(all(item.status == "pass" for item in analyze_semantics(request, analyzer=FixtureAnalyzer()).claims))
        for lineage in ("target_derived", "circular", "unknown"):
            analyzer = FixtureAnalyzer()
            result = analyze_semantics(replace(request, pairs=(replace(request.pairs[0], reference_lineage=lineage),)), analyzer=analyzer)
            self.assertEqual(analyzer.calls, [])
            self.assertTrue(all(item.status == "unknown" for item in result.claims))

    def test_canonical_validation_source_hash_and_image_revision_exact(self):
        request = request_fixture()
        changed = replace(request.view_set, canonical_reference=replace(request.view_set.canonical_reference, validated=False))
        self.assertEqual(analyze_semantics(replace(request, view_set=changed), analyzer=FixtureAnalyzer()).state, "insufficient_evidence")
        stale = replace(request, pairs=(replace(request.pairs[0], target_image_sha256="e"*64),))
        self.assertTrue(all(item.status == "unknown" for item in analyze_semantics(stale, analyzer=FixtureAnalyzer()).claims))
        bad_image = replace(request.images[0].source, sha256="e"*64)
        old = request.images[0]
        mismatched = make_semantic_image(view_id=old.view_id, source=bad_image,
            original_decoded_sha256=old.original_decoded_sha256, source_width=16, source_height=16,
            width=16, height=16, rgba=old.rgba)
        result = analyze_semantics(replace(request, images=(mismatched, request.images[1])), analyzer=FixtureAnalyzer())
        self.assertEqual(result.state, "invalid_request")

    def test_stale_response_model_mismatch_and_changed_regions_abstain(self):
        for transform, state in (
            (lambda response, _: replace(response, request_fingerprint="e"*64), "stale_response"),
            (lambda response, _: replace(response, model=EngineVersion("other.model", "different")), "model_mismatch"),
            (lambda response, _: replace(response, claims=(replace(response.claims[0], target=Region("target", "different", (.1,.1,.9,.9))),)), "malformed_response"),
        ):
            result = analyze_semantics(request_fixture(), analyzer=FixtureAnalyzer(transform))
            self.assertEqual(result.state, state)
            self.assertTrue(all(item.status == "unknown" for item in result.claims))
            self.assertIsNotNone(result.raw_response_sha256)

    def test_late_response_is_retained_as_unknown_not_hard_timeout_claim(self):
        analyzer = FixtureAnalyzer()
        with patch("core.appearance_diagnostics.semantics.time.monotonic", side_effect=[0., .1, .2, 2., 2.1]):
            result = analyze_semantics(request_fixture(), analyzer=analyzer, timeout_seconds=1.)
        self.assertEqual(result.state, "timed_out")
        self.assertIsNotNone(result.raw_response_sha256)
        self.assertTrue(all(item.status == "unknown" for item in result.claims))
        self.assertAlmostEqual(analyzer.calls[0][1], .8)

    def test_cancellation_before_and_after_adapter_preserves_returned_raw(self):
        request, analyzer = request_fixture(), FixtureAnalyzer()
        result = analyze_semantics(request, analyzer=analyzer, cancel=lambda: True)
        self.assertEqual(result.state, "cancelled")
        self.assertEqual(analyzer.calls, [])
        event = {"cancel": False}
        def cancelled_response(response, _):
            event["cancel"] = True
            return response
        result = analyze_semantics(request, analyzer=FixtureAnalyzer(cancelled_response), cancel=lambda: event["cancel"])
        self.assertEqual(result.state, "cancelled")
        self.assertIsNotNone(result.raw_response_sha256)
        self.assertTrue(all(item.status == "unknown" for item in result.claims))

    def test_unavailable_malformed_service_and_bounded_response_errors(self):
        class Broken(FixtureAnalyzer):
            def analyze(self, *args, **kwargs):
                raise RuntimeError("provider credential or stack must not be copied "*100)
        result = analyze_semantics(request_fixture(), analyzer=Broken())
        self.assertEqual(result.state, "service_error")
        self.assertNotIn("credential", result.error_message)
        malformed = FixtureAnalyzer(lambda *_: {"schema_version": 2})
        result = analyze_semantics(request_fixture(), analyzer=malformed)
        self.assertEqual(result.state, "malformed_response")
        self.assertIsNotNone(result.raw_response_sha256)
        oversized = FixtureAnalyzer(lambda *_: {"huge": "x"*600000})
        result = analyze_semantics(request_fixture(), analyzer=oversized)
        self.assertEqual(result.state, "malformed_response")
        self.assertIsNone(result.raw_response_sha256)
        self.assertLessEqual(len(result.error_message), 512)
        for timeout in (True, float("nan"), float("inf"), 0, 121):
            self.assertEqual(analyze_semantics(request_fixture(), analyzer=FixtureAnalyzer(), timeout_seconds=timeout).state, "invalid_request")

    def test_host_unavailability_and_metadata_malformed_are_explicit_unknown(self):
        class Unavailable(FixtureAnalyzer):
            def analyze(self, *args, **kwargs):
                raise SemanticAnalyzerUnavailable("External service not ready.")
        result = analyze_semantics(request_fixture(), analyzer=Unavailable())
        self.assertEqual(result.state, "unavailable")
        self.assertTrue(all(item.status == "unknown" for item in result.claims))
        self.assertIsNotNone(result.model)
        class BadMetadata(FixtureAnalyzer):
            def metadata(self):
                return {"schema_version": 2}
        result = analyze_semantics(request_fixture(), analyzer=BadMetadata())
        self.assertEqual(result.state, "malformed_response")
        self.assertTrue(all(item.status == "unknown" for item in result.claims))

    def test_raw_response_hash_tampering_is_rejected_on_restore(self):
        result = analyze_semantics(request_fixture(), analyzer=FixtureAnalyzer())
        forged = result.to_dict()
        forged["raw_response_json"] = "{}"
        with self.assertRaises(ValueError):
            SemanticEvaluation.from_dict(forged)

    def test_semantic_model_judgments_never_override_geometry_or_export_findings(self):
        request = request_fixture()
        evaluation = analyze_semantics(request, analyzer=FixtureAnalyzer(), policy=SemanticPolicy(required=True))
        failed_geometry = Finding("geometry-proof", "geometry.cross_view_conflict", "geometry", "error", "fail",
            "Deterministic geometry remains failed.", evidence=(Evidence("geometry-measurement", "observation",
                "Synthetic contract measurement only.", measurements=(Measurement("missing_pixels", 20, "pixel"),)),))
        report = DiagnosticReport("combined", request.view_set, evaluation.engines,
            DiagnosticPolicy("semantic-contract-fixture", "1", "f"*64), DiagnosticResolution(16,16),
            evaluation.findings+(failed_geometry,))
        self.assertEqual(report.verification_status, "fail")
        export_unknown = Finding("export-proof", "quality.export_check", "quality", "warning", "unknown",
            "Export was not evaluated.", reason="No export inspection occurred.")
        report = replace(report, findings=evaluation.findings+(export_unknown,))
        self.assertEqual(report.verification_status, "unknown")


if __name__ == "__main__":
    unittest.main()
