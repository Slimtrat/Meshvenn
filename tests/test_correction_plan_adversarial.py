"""Independent correction-plan checks against measured D4 and D1 contracts."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from core.correction_plans import (CorrectionPlan, CorrectionPolicy, EditAnnotation, ProviderCapabilities,
    plan_corrections, prepare_correction)
from core.diagnostic_contracts import (ArtifactReference, DiagnosticPolicy, DiagnosticReport,
    EngineVersion, Evidence, Finding, Measurement, Region)
from core.diagnostic_contracts.codec import fingerprint
from core.geometry_diagnostics.models import MaskArtifact
from core.image_mask import BinaryMask
from core.projection_alignment import ProjectionAlignment
from tests.test_appearance_engine import run


PROOF = ArtifactReference("review-annotation", "d"*64, "application/json")
CAPABILITIES = ProviderCapabilities("review-provider", "1",
    ("region_edit","mask","multiple_references","camera_request","identity_reference"))


def finding(code, *, category="input", status="fail", ids=("target",), regions=(), name="review-finding"):
    evidence = Evidence("e-"+name,"observation","Synthetic declared check for planner routing only.",
        ids,regions,measurements=(Measurement("supported",1,"count"),))
    return Finding(name,code,category,"warning",status,"Planner routing fixture.",ids,regions,
                   evidence=(evidence,),reason="Explicit unresolved evidence." if status=="unknown" else "")


def report(view_set, *findings, engine="meshvenn.diagnostics_preflight"):
    from core.diagnostic_contracts import DiagnosticResolution
    return DiagnosticReport("review-"+fingerprint([f.to_dict() for f in findings])[:20],view_set,
        (EngineVersion(engine,"1"),),DiagnosticPolicy("review-policy","1","b"*64,
            tuple(dict.fromkeys(f.code for f in findings))),DiagnosticResolution(32,32),tuple(findings))


def edits(result):
    return tuple(plan for plan in result.plans if plan.action_kind=="edit_region")


class CorrectionPlanAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Actual triangle visibility and changed immutable source buffers, not
        # a manually assigned aggregate appearance verdict.
        cls.appearance = run(changed=True)
        cls.views = cls.appearance.report.view_set

    def plan(self, reports, *, view_set=None, **kwargs):
        return plan_corrections(view_set or self.views,reports,capabilities=CAPABILITIES,**kwargs)

    def test_visible_color_failure_localizes_observation_without_editing_canonical(self):
        result = self.plan((self.appearance.report,))
        proposed = edits(result)
        self.assertTrue(proposed)
        for plan in proposed:
            self.assertEqual(plan.readiness,"ready")
            self.assertEqual(plan.target.view_id,"target")
            self.assertNotEqual(plan.target.bounds,(0.,0.,1.,1.))
            self.assertEqual(plan.prompt.original.view_id,"target")
            self.assertEqual(tuple(v.view_id for v in plan.prompt.references),("reference",))
            self.assertIsNone(plan.prompt.annotation)  # No mask is fabricated from this measured box.
            self.assertIn("identity",{item.kind for item in plan.prompt.invariants})
            self.assertIn("verify_identity",{item.kind for item in plan.prompt.postconditions})
        self.assertEqual(result.verification_status,"unknown")
        self.assertEqual(self.appearance.identity_status,"unknown")

    def test_reference_input_preparation_blocks_edits_using_that_reference(self):
        bad_reference = report(self.views,finding("input.hash_mismatch",ids=("reference",)))
        result = self.plan((self.appearance.report,bad_reference))
        self.assertEqual(len(edits(result)),0)
        self.assertIn("inspect_input",{p.action_kind for p in result.plans})

    def test_target_framing_and_mask_repairs_take_priority_over_color_edit(self):
        for code, action in (("input.subject_truncated","prepare_alignment"),
                             ("input.empty_mask","repair_mask")):
            with self.subTest(code=code):
                preparation = report(self.views,finding(code))
                result = self.plan((self.appearance.report,preparation))
                self.assertFalse(edits(result))
                self.assertIn(action,{p.action_kind for p in result.plans})

    def test_engine_failure_never_routes_to_regeneration(self):
        failure = report(self.views,finding("engine.native_unavailable",category="engine",status="unknown"),
                         engine="meshvenn.geometry_diagnostics")
        result = self.plan((self.appearance.report,failure))
        self.assertFalse(edits(result))
        self.assertIn("diagnose_engine",{p.action_kind for p in result.plans})

    def test_geometry_group_conflict_does_not_choose_a_faulty_view(self):
        conflict = report(self.views,finding("geometry.cross_view_conflict",category="geometry",
            ids=("target","reference"),regions=(Region("target","measured",(.2,.2,.4,.4)),)),
            engine="meshvenn.geometry_diagnostics")
        result = self.plan((conflict,))
        self.assertFalse(edits(result))
        self.assertIn("select_reference",{p.action_kind for p in result.plans})

    def geometry_evidence(self):
        # Same geometric camera, independently hashed verification artifacts.
        changed_views = tuple(replace(v,camera=replace(v.camera,verification_evidence=
            replace(PROOF,artifact_id="camera-"+v.view_id,sha256=("e" if v.view_id=="target" else "f")*64)),
            alignment=ProjectionAlignment(.12,-.04,1.1) if v.view_id=="target" else v.alignment)
            for v in self.views.views)
        revision = replace(self.views,views=changed_views)
        global_conflict = finding("geometry.reference_conflict",category="geometry",
                                  ids=("target","reference"),name="canonical-conflict")
        detail = finding("geometry.detail_preservation",category="geometry",ids=("target","reference"),
            regions=(Region("target","aligned-component",(.2,.2,.4,.4)),),name="canonical-detail")
        diagnostic = report(revision,global_conflict,detail,engine="meshvenn.geometry_diagnostics")
        original = Region("target","authored-original-support",(.6,.3,.75,.5))
        annotation = EditAnnotation(fingerprint(diagnostic.to_dict()),detail.finding_id,original,PROOF)
        return revision,diagnostic,annotation

    def test_aligned_geometry_needs_original_annotation_and_distinct_camera_proofs_are_valid(self):
        revision,diagnostic,annotation = self.geometry_evidence()
        self.assertFalse(edits(self.plan((diagnostic,),view_set=revision)))
        result = self.plan((diagnostic,),view_set=revision,annotations=(annotation,))
        self.assertTrue(edits(result))
        self.assertTrue(all(p.target==annotation.region and p.prompt.annotation==annotation for p in edits(result)))

    def test_annotation_binds_full_report_content_not_only_dependency_fingerprint(self):
        revision,diagnostic,annotation = self.geometry_evidence()
        altered = replace(diagnostic,findings=tuple(replace(f,message="Changed measured evidence.")
                                                  for f in diagnostic.findings))
        self.assertEqual(altered.dependency_fingerprint,diagnostic.dependency_fingerprint)
        self.assertNotEqual(fingerprint(altered.to_dict()),fingerprint(diagnostic.to_dict()))
        with self.assertRaises(ValueError):
            self.plan((altered,),view_set=revision,annotations=(annotation,))

    def test_competing_same_camera_canonical_evidence_requires_reference_choice(self):
        revision,_,_ = self.geometry_evidence()
        target = next(v for v in revision.views if v.view_id=="target")
        reference = replace(next(v for v in revision.views if v.view_id=="reference"),camera=target.camera)
        second = replace(reference,view_id="reference-two",image=replace(reference.image,sha256="9"*64))
        revision = replace(revision,views=(target,reference,second),input_order=(),
            canonical_reference=replace(revision.canonical_reference,view_ids=("reference","reference-two")))
        disagreement = finding("geometry.reference_conflict",category="geometry",
                               ids=("target","reference"),name="first-reference-fail")
        agreement = finding("geometry.reference_conflict",category="geometry",status="pass",
                            ids=("target","reference-two"),name="second-reference-pass")
        detail = finding("geometry.detail_preservation",category="geometry",ids=("target","reference"),
            regions=(Region("target","aligned-detail",(.2,.2,.4,.4)),),name="annotated-detail")
        diagnostic = report(revision,disagreement,agreement,detail,engine="meshvenn.geometry_diagnostics")
        annotation = EditAnnotation(fingerprint(diagnostic.to_dict()),detail.finding_id,
                                   Region("target","source-support",(.6,.3,.75,.5)),PROOF)
        result = self.plan((diagnostic,),view_set=revision,annotations=(annotation,))
        self.assertEqual(len(edits(result)),0)
        self.assertIn("select_reference",{p.action_kind for p in result.plans})

    def test_missing_provider_controls_are_preserved_as_explicit_unsupported_requirements(self):
        result = plan_corrections(self.views,(self.appearance.report,),
            capabilities=ProviderCapabilities("limited-provider","1",("region_edit",)))
        proposed = edits(result)
        self.assertTrue(proposed)
        for plan in proposed:
            self.assertEqual(plan.readiness,"unsupported")
            self.assertTrue(plan.unsupported_controls)
            self.assertTrue(plan.alternative)
            self.assertTrue(set(plan.unsupported_controls)<=set(plan.required_controls))

    def test_explicit_original_mask_is_preserved_and_requires_provider_mask_support(self):
        diagnostic = self.appearance.report
        local = next(f for f in diagnostic.findings if f.code=="appearance.color_consistency" and
            f.status=="fail" and any(r.view_id=="target" and r.label.startswith("visible-difference") for r in f.regions))
        region = next(r for r in local.regions if r.view_id=="target")
        pixels = bytearray(32*32)
        pixels[16*32+16] = 1
        mask = MaskArtifact.from_mask(BinaryMask(32,32,bytes(pixels)))
        annotation = EditAnnotation(fingerprint(diagnostic.to_dict()),local.finding_id,region,PROOF,mask)
        result = self.plan((diagnostic,),annotations=(annotation,))
        plan = edits(result)[0]
        self.assertEqual(plan.prompt.annotation.mask,mask)
        self.assertIn("mask",plan.required_controls)
        no_masks = replace(CAPABILITIES,controls=tuple(c for c in CAPABILITIES.controls if c!="mask"))
        unsupported = edits(plan_corrections(self.views,(diagnostic,),annotations=(annotation,),capabilities=no_masks))[0]
        self.assertEqual(unsupported.readiness,"unsupported")
        self.assertIn("mask",unsupported.unsupported_controls)
        self.assertEqual(unsupported.prompt.annotation.mask,mask)

    def test_reference_budget_never_silently_discards_accepted_references(self):
        from core.appearance_diagnostics import AppearancePolicy,analyze_appearance
        from tests.test_appearance_engine import fixture,SETTINGS
        revision,inputs,surface = fixture(changed=True)
        original = next(v for v in revision.views if v.view_id=="reference")
        second = replace(original,view_id="reference-two")
        revision = replace(revision,views=(*revision.views,second),input_order=(),
            canonical_reference=replace(revision.canonical_reference,view_ids=("reference","reference-two")))
        inputs = {**inputs,"reference-two":inputs["reference"]}
        measured = analyze_appearance(revision,inputs,surface=surface,
            view_settings={key:SETTINGS for key in inputs},policy=AppearancePolicy(sampling_size=32))
        result = plan_corrections(revision,(measured.report,),capabilities=replace(CAPABILITIES,max_references=1))
        self.assertTrue(edits(result))
        for plan in edits(result):
            self.assertEqual(plan.readiness,"unsupported")
            self.assertIn("multiple_references",plan.unsupported_controls)
            self.assertEqual({r.view_id for r in plan.prompt.references},{"reference","reference-two"})

    def test_prepare_recomputes_originals_references_and_unknown_quality(self):
        plan = edits(self.plan((self.appearance.report,)))[0]
        restored = CorrectionPlan.from_json(plan.to_json())
        prepared = prepare_correction(restored,self.views,(self.appearance.report,),capabilities=CAPABILITIES)
        self.assertEqual(prepared.verification_status,"unknown")
        self.assertEqual(prepared.candidate_origin,"derived")
        self.assertEqual(prepared.prompt,plan.prompt)
        self.assertEqual(prepared.postconditions,plan.prompt.postconditions)
        self.assertEqual(set(prepared.derived_from),{v.image.sha256 for v in self.views.views})

    def test_copying_context_and_plan_id_cannot_remove_protected_region_invariant(self):
        plan = edits(self.plan((self.appearance.report,)))[0]
        forged = replace(plan,prompt=replace(plan.prompt,invariants=tuple(
            invariant for invariant in plan.prompt.invariants if invariant.kind!="outside_region")))
        self.assertEqual(forged.plan_id,plan.plan_id)
        self.assertEqual(forged.context_sha256,plan.context_sha256)
        with self.assertRaises(ValueError):
            prepare_correction(forged,self.views,(self.appearance.report,),capabilities=CAPABILITIES)

    def test_prepare_rejects_changed_camera_alignment_mask_policy_capability_and_report(self):
        plan = edits(self.plan((self.appearance.report,)))[0]
        target = next(v for v in self.views.views if v.view_id=="target")
        for change in (replace(target,camera=replace(target.camera,azimuth_degrees=15.)),
                       replace(target,alignment=ProjectionAlignment(.03,0.,1.)),
                       replace(target,mask=replace(target.image,sha256="8"*64))):
            current = replace(self.views,views=tuple(change if v.view_id=="target" else v for v in self.views.views))
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_correction(plan,current,(self.appearance.report,),capabilities=CAPABILITIES)
        for kwargs in ({"policy":CorrectionPolicy(max_plans=32)},
                       {"capabilities":replace(CAPABILITIES,version="changed")},
                       {"reports":(replace(self.appearance.report,completion="cancelled"),)}):
            arguments=dict(reports=(self.appearance.report,),capabilities=CAPABILITIES)
            arguments.update(kwargs)
            with self.subTest(change=kwargs), self.assertRaises(ValueError):
                prepare_correction(plan,self.views,**arguments)

    def test_nonedit_and_unsupported_plans_cannot_be_prepared_as_provider_edits(self):
        result = self.plan((self.appearance.report,))
        manual = next(p for p in result.plans if p.action_kind!="edit_region")
        with self.assertRaises(ValueError):
            prepare_correction(manual,self.views,(self.appearance.report,),capabilities=CAPABILITIES)
        unsupported_caps = ProviderCapabilities("unsupported","1",())
        unsupported = edits(plan_corrections(self.views,(self.appearance.report,),capabilities=unsupported_caps))[0]
        with self.assertRaises(ValueError):
            prepare_correction(unsupported,self.views,(self.appearance.report,),capabilities=unsupported_caps)

    def test_report_hashing_is_inside_the_declared_deadline(self):
        from core.correction_plans import engine
        clock = [0.]
        original_fingerprint = engine.fingerprint
        clean = replace(self.appearance.report,findings=(),policy=replace(self.appearance.report.policy,required_checks=()))
        def costly_reflection(value):
            if type(value) is dict and "report_id" in value:
                clock[0] += 1.
            return original_fingerprint(value)
        with patch.object(engine.time,"monotonic",side_effect=lambda:clock[0]), \
                patch.object(engine,"fingerprint",side_effect=costly_reflection):
            try:
                result = plan_corrections(self.views,(clean,),capabilities=CAPABILITIES,
                                          policy=CorrectionPolicy(max_seconds=.001))
            except TimeoutError:
                return  # A bounded pre-planning timeout may reject the request.
        self.assertEqual(result.completion,"partial")


if __name__ == "__main__":
    unittest.main()
