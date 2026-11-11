from __future__ import annotations

import json
import math
import unittest
from dataclasses import FrozenInstanceError, replace

from core.diagnostic_contracts import (
    ArtifactReference, CameraDeclaration, Category, DiagnosticPolicy, DiagnosticReport,
    DiagnosticResolution, EngineVersion, Evidence, Finding, Judgment, Measurement,
    ProposedAction, Region, Threshold, VerificationStatus, ViewRevision, ViewSetRevision,
    content_sha256,
)
from core.projection_alignment import ProjectionAlignment
from core.projection_frame import native_projection_frame
from core.projection_math import compile_projection
from tests.diagnostic_contracts_test_support import observed_finding, report, source, view_set


class DiagnosticSerializationTests(unittest.TestCase):
    def test_full_report_roundtrip_preserves_typed_evidence_and_interpretation(self):
        region = Region("front", "left-arm", (.1, .2, .4, .8))
        model = EngineVersion("identity-analyzer", "2026-11")
        evidence = Evidence("contour", "observation", "Reprojection misses a visible arm region.",
                            ("front",), (region,),
                            (Measurement("missing_fraction", .2, "ratio", Threshold("<=", .05, "ratio")),),
                            ArtifactReference("heatmap", "2" * 64, "image/png", "artifacts/heatmap.png"))
        finding = Finding("cross-view", "geometry.cross_view_conflict", "geometry", "error", "fail",
                          "The declared views do not preserve the arm silhouette.", ("front", "side"),
                          (region,), (evidence,),
                          (Judgment("The profile may shorten the arm.", "model", "The canonical image does not disambiguate depth.", model, .7),),
                          (ProposedAction("reference-choice", "select_reference", "Confirm the intended arm length.", ("front",), (region,)),))
        original = report(engines=(model, EngineVersion("preflight", "1.0")),
                          findings=(finding, observed_finding()))
        restored = DiagnosticReport.from_json(original.to_json())
        self.assertEqual(original, restored)
        self.assertEqual(original.to_json(), restored.to_json())
        self.assertIsInstance(restored.findings[0].category, Category)
        self.assertIsInstance(restored.view_set.views[0].alignment, ProjectionAlignment)
        self.assertEqual(restored.verification_status, VerificationStatus.FAIL)
        self.assertEqual(json.loads(original.to_json()), original.to_dict())
        self.assertFalse(restored.findings[0].interpretations[0].confidence_calibrated)

    def test_view_set_roundtrip_keeps_provenance_order_and_stable_ids(self):
        original = replace(view_set(), input_order=("side", "front"))
        restored = ViewSetRevision.from_json(original.to_json())
        self.assertEqual(original, restored)
        self.assertEqual(restored.input_order, ("side", "front"))
        self.assertEqual(tuple(v.view_id for v in restored.views), ("front", "side"))

    def test_unknown_fields_missing_versions_and_unsupported_versions_are_rejected(self):
        for path in ((), ("view_set",)):
            for change in ("extra", "missing-version", "version"):
                data = report().to_dict()
                target = data
                for key in path:
                    target = target[key]
                if change == "extra":
                    target["silently_ignored"] = True
                elif change == "missing-version":
                    del target["schema_version"]
                else:
                    target["schema_version"] = 2
                with self.subTest(path=path, change=change), self.assertRaises(ValueError):
                    DiagnosticReport.from_dict(data)

    def test_malformed_json_duplicate_fields_and_nonfinite_numbers_are_rejected(self):
        for payload in ("{", "[]", "null", '{"schema_version":1,"schema_version":1}',
                        report().to_json().replace('"value":768.0', '"value":NaN'),
                        report().to_json().replace('"value":768.0', '"value":Infinity'),
                        report().to_json().replace('"value":768.0', '"value":1e999')):
            with self.subTest(payload=payload[:100]), self.assertRaises(ValueError):
                DiagnosticReport.from_json(payload)

    def test_scalar_types_and_nested_schema_are_strict(self):
        cases = (
            ("schema_version", True), ("schema_version", "1"), ("completion", "finished"),
            ("findings", {}), ("report_id", None),
        )
        for key, value in cases:
            data = report().to_dict()
            data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                DiagnosticReport.from_dict(data)
        data = report().to_dict()
        data["view_set"]["views"][0]["alignment"]["scale"] = True
        with self.assertRaises(ValueError):
            DiagnosticReport.from_dict(data)

    def test_frozen_normalized_copies_prevent_mutable_list_changes(self):
        findings = [observed_finding()]
        value = report(findings=findings)
        findings.clear()
        self.assertEqual(len(value.findings), 1)
        with self.assertRaises(FrozenInstanceError):
            value.report_id = "changed"

    def test_existing_projection_authorities_are_reused(self):
        camera = view_set().views[0].camera
        self.assertEqual(camera.transform, compile_projection(azimuth_degrees=0, elevation_degrees=0))
        self.assertEqual(camera.native_frame(2, 64, 48), native_projection_frame(2, 0, 0, 64, 48))
        with self.assertRaises(ValueError):
            CameraDeclaration("perspective", 0, 0).transform
        with self.assertRaises(ValueError):
            CameraDeclaration("orthographic", 0, 0, verified=True)
        with self.assertRaises(ValueError):
            CameraDeclaration("perspective", 0, 0, verified=True,
                              verification_evidence=ArtifactReference("proof", "a" * 64, "application/json"))


class EvidenceValidationTests(unittest.TestCase):
    def test_nonfinite_data_is_rejected_in_every_numeric_contract(self):
        factories = (
            lambda v: Measurement("area", v, "pixel"),
            lambda v: Threshold("<=", v, "pixel"),
            lambda v: CameraDeclaration("orthographic", v, 0),
            lambda v: Region("front", "arm", (0, 0, v, 1)),
            lambda v: Judgment("Possible drift.", "inference", "No hidden-region evidence.", confidence=v),
        )
        for number in (math.nan, math.inf, -math.inf, True):
            for factory in factories:
                with self.subTest(number=number, factory=factory), self.assertRaises(ValueError):
                    factory(number)

    def test_pass_fail_cannot_exist_without_evidence(self):
        for status in ("pass", "fail"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                Finding("check", "geometry.cross_view_conflict", "geometry", "error", status, "Claim without proof.")
        with self.assertRaises(ValueError):
            Evidence("proof", "observation", "A narrative is not a measurement.")
        with self.assertRaises(ValueError):
            Evidence("proof", "artifact", "A missing artifact cannot support the claim.")

    def test_unknown_and_not_applicable_require_a_reason(self):
        for status in ("unknown", "not_applicable"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                Finding("check", "appearance.identity_drift", "appearance", "warning", status, "No conclusion.")
        finding = Finding("hidden", "appearance.identity_drift", "appearance", "info", "not_applicable",
                          "Hidden regions are excluded from this color comparison.",
                          reason="The region is occluded in all declared comparison cameras.")
        self.assertEqual(report(findings=(observed_finding(), finding)).verification_status, VerificationStatus.PASS)

    def test_units_targets_and_identifiers_are_validated(self):
        with self.assertRaises(ValueError):
            Measurement("area", 4, "pixel", Threshold(">", 1, "ratio"))
        with self.assertRaises(ValueError):
            Region("front", "outside", (0, 0, 2, 1))
        with self.assertRaises(ValueError):
            replace(observed_finding(), code="Input Empty Mask")
        with self.assertRaises(ValueError):
            report(findings=(replace(observed_finding(), view_ids=("not-in-set",)),))
        with self.assertRaises(ValueError):
            report(findings=(replace(observed_finding(), evidence=(
                Evidence("bad", "observation", "Unknown source view.", ("not-in-set",),
                         measurements=(Measurement("area", 1, "pixel"),)),)),))

    def test_model_judgments_require_version_and_calibration_proof(self):
        with self.assertRaises(ValueError):
            Judgment("Same identity.", "model", "Not calibrated.")
        with self.assertRaises(ValueError):
            Judgment("Same identity.", "model", "No validation evidence.",
                     EngineVersion("vision", "1"), .9, True)
        model_judgment = Judgment("Possible identity drift.", "model", "Visible texture is poorly lit.", EngineVersion("vision", "1"), .6)
        with self.assertRaises(ValueError):
            report(findings=(replace(observed_finding(), interpretations=(model_judgment,)),))


class ConservativeConclusionTests(unittest.TestCase):
    def test_unavailable_model_is_unknown_even_if_geometric_check_passes(self):
        missing_model = Finding("identity", "appearance.identity_drift", "appearance", "warning", "unknown",
                                "Identity analysis was not run.", reason="Optional vision model is unavailable.")
        value = report(findings=(observed_finding(), missing_model))
        self.assertEqual(value.verification_status, VerificationStatus.UNKNOWN)
        self.assertEqual(DiagnosticReport.from_json(value.to_json()), value)

    def test_ambiguous_conflict_keeps_observation_without_attributing_fault(self):
        conflict = Finding("ambiguous", "geometry.cross_view_conflict", "geometry", "warning", "unknown",
                           "Two views disagree on limb extent.", ("front", "side"),
                           evidence=(Evidence("overlap", "observation", "Shared reprojection overlap.",
                                              ("front", "side"), measurements=(Measurement("iou", .4, "ratio"),)),),
                           interpretations=(Judgment("Either view could match the intended shape.", "inference", "No canonical depth reference disambiguates the pair."),),
                           reason="The discrepancy does not identify which view is correct.")
        value = report(findings=(observed_finding(), conflict))
        self.assertEqual(value.verification_status, VerificationStatus.UNKNOWN)
        self.assertEqual(value.findings[0].view_ids, ("front", "side"))

    def test_engine_failure_cancelled_and_partial_runs_never_qualify_as_pass(self):
        for state in ("failed", "partial", "cancelled"):
            with self.subTest(state=state):
                value = report(completion=state)
                self.assertEqual(value.verification_status, VerificationStatus.UNKNOWN)
                self.assertEqual(DiagnosticReport.from_json(value.to_json()).completion, state)

    def test_missing_required_checks_and_unknown_regions_cannot_hide_behind_pass(self):
        policy = replace(report().policy, required_checks=("input.empty_mask", "geometry.cross_view_conflict"))
        value = report(policy=policy)
        self.assertEqual(value.missing_required_checks, ("geometry.cross_view_conflict",))
        self.assertEqual(value.verification_status, VerificationStatus.UNKNOWN)
        unknown = replace(observed_finding(), finding_id="unmeasured-region", status="unknown",
                          evidence=(), reason="The smaller region has no coverage.")
        self.assertEqual(report(findings=(observed_finding(), unknown)).verification_status, VerificationStatus.UNKNOWN)
        failed = replace(observed_finding(), finding_id="failed-region", status="fail")
        self.assertEqual(report(findings=(observed_finding(), failed)).verification_status, VerificationStatus.FAIL)

    def test_empty_reports_do_not_pass_and_explicit_exemptions_are_distinct(self):
        self.assertEqual(report(findings=()).verification_status, VerificationStatus.UNKNOWN)
        exemption = replace(observed_finding(), status="not_applicable", evidence=(), reason="This profile excludes source masks for mesh-only input.")
        self.assertEqual(report(findings=(exemption,)).verification_status, VerificationStatus.NOT_APPLICABLE)

    def test_blocking_findings_cannot_be_optional_and_empty_engines_cannot_certify(self):
        blocked = replace(observed_finding(), finding_id="blocked", code="quality.export_failed",
                          severity="blocking", status="fail", required=False)
        self.assertEqual(report(findings=(observed_finding(), blocked)).verification_status, VerificationStatus.FAIL)
        unknown = replace(blocked, status="unknown", reason="Export reload was unavailable.")
        self.assertEqual(report(findings=(observed_finding(), unknown)).verification_status, VerificationStatus.UNKNOWN)
        self.assertEqual(report(engines=()).verification_status, VerificationStatus.UNKNOWN)


class DependencyInvalidationTests(unittest.TestCase):
    def test_all_semantic_source_and_run_dependencies_invalidate_report(self):
        original = report()
        views = original.view_set.views
        front = views[0]
        variants = (
            replace(front, image=source("3")), replace(front, mask=source("4")),
            replace(front, image=source(width=65)),
            replace(front, camera=replace(front.camera, azimuth_degrees=5)),
            replace(front, alignment=ProjectionAlignment(.01, 0, 1)),
            replace(front, revision=4), replace(front, origin="generated"),
        )
        for changed in variants:
            current = replace(original.view_set, views=(changed, views[1]))
            with self.subTest(changed=changed):
                self.assertTrue(original.is_stale(current))
                with self.assertRaises(ValueError):
                    original.require_current(current)
        reference = original.view_set.canonical_reference
        for changed_reference in (replace(reference, revision=3), replace(reference, content=source("5")),
                                  replace(reference, validated=False)):
            self.assertTrue(original.is_stale(replace(original.view_set, canonical_reference=changed_reference)))
        for dependencies in (
            {"policy": replace(original.policy, version="2")},
            {"policy": replace(original.policy, configuration_sha256="6" * 64)},
            {"engines": (EngineVersion("preflight", "2.0"),)},
            {"resolution": DiagnosticResolution(32, 24)},
            {"assumptions": ("Symmetry is assumed.",)},
        ):
            with self.subTest(dependencies=dependencies):
                self.assertTrue(original.is_stale(original.view_set, **dependencies))

    def test_order_and_artifact_relocation_are_provenance_only(self):
        original = report()
        permuted = replace(original.view_set, views=tuple(reversed(original.view_set.views)), input_order=("side", "front"))
        self.assertFalse(original.is_stale(permuted))
        self.assertNotEqual(original.view_set.to_json(), permuted.to_json())
        front, side = original.view_set.views
        relocated = replace(front.camera.verification_evidence, uri="moved/camera.json")
        moved = replace(original.view_set, views=(replace(front, camera=replace(front.camera, verification_evidence=relocated)), side))
        self.assertFalse(original.is_stale(moved))

    def test_hashes_are_exact_content_hashes_and_json_is_canonical(self):
        self.assertEqual(content_sha256(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        original = report()
        self.assertEqual(original.dependency_fingerprint, DiagnosticReport.from_json(original.to_json()).dependency_fingerprint)
        self.assertNotIn(" ", original.to_json().split('"assumptions"')[0])
        with self.assertRaises(ValueError):
            content_sha256("abc")


if __name__ == "__main__":
    unittest.main()
