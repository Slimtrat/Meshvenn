"""Real D4 surface/color composition and conservative failure propagation."""
from __future__ import annotations

import unittest
from dataclasses import replace

from core.appearance_diagnostics import (AppearancePolicy, AppearanceRegionAnchor,
    AppearanceResult, AppearanceViewSettings, SurfaceMesh, analyze_appearance)
from core.diagnostic_contracts import (ArtifactReference, CameraDeclaration, CanonicalReference,
    ContentReference, DiagnosticPolicy, DiagnosticReport, DiagnosticResolution,
    EngineVersion, Evidence, Finding, Measurement, Region, ViewRevision, ViewSetRevision)
from core.diagnostics_preflight import RasterInput, ViewInput

PROOF = ArtifactReference("analytic-fixture","a"*64,"application/json")
SETTINGS = AppearanceViewSettings("scene-linear","albedo",1.,True,PROOF)


def fixture(changed=False):
    size = 32
    def raster(change):
        values = []
        for y in range(size):
            for x in range(size):
                inside = 4<=x<28 and 4<=y<28
                rgb = (.8,.15,.2) if change and 12<=x<20 and 12<=y<20 else (.2,.55,.4)
                values.extend((*rgb,1.) if inside else (0.,0.,0.,0.))
        return RasterInput.from_pixels(size,size,values)
    target,reference = raster(changed),raster(False)
    def view(name,image,role):
        return ViewRevision(name,1,ContentReference(image.source_sha256,size,size,image.media_type),None,
            CameraDeclaration("orthographic",0.,0.,False,True,PROOF),role=role)
    views = (view("target",target,"observation"),view("reference",reference,"reference"))
    revision = ViewSetRevision("appearance-test",1,views,
        CanonicalReference("accepted",1,views[1].image,True,("reference",),PROOF))
    mesh = SurfaceMesh(((-.8,0.,-.8),(.8,0.,-.8),(.8,0.,.8),(-.8,0.,.8)),((0,1,2),(0,2,3)),PROOF)
    return revision,{"target":ViewInput(target),"reference":ViewInput(reference)},mesh


def run(*,changed=False,**kwargs):
    view_set,inputs,mesh = fixture(changed)
    return analyze_appearance(view_set,inputs,surface=mesh,
        view_settings={key:SETTINGS for key in inputs},policy=AppearancePolicy(sampling_size=32),**kwargs)


class AppearanceEngineTests(unittest.TestCase):
    def test_same_colors_are_local_pass_but_identity_unknown(self):
        result = run()
        self.assertTrue(result.views)
        self.assertTrue(all(r.color_status=="pass" for v in result.views for r in v.regions))
        self.assertEqual("unknown",result.identity_status)
        self.assertEqual("unknown",result.report.verification_status)
        self.assertEqual(result,AppearanceResult.from_dict(result.to_dict()))

    def test_visible_local_color_change_fails_even_with_no_model(self):
        result = run(changed=True)
        self.assertEqual("fail",result.report.verification_status)
        self.assertTrue(any(r.region.label.startswith("visible-difference") and r.color_status=="fail"
                            for view in result.views for r in view.regions))

    def test_unknown_roi_does_not_certify_whole_frame(self):
        result = run(regions=(Region("target","unlocated-accessory"),))
        region = next(r for r in result.views[0].regions if r.region.label=="unlocated-accessory")
        self.assertEqual("unknown",region.color_status)
        self.assertEqual("unknown",region.coverage_status)

    def test_occluded_expected_feature_does_not_validate_foreground(self):
        region = Region("target","expected-behind",(.3,.3,.7,.7))
        anchor = AppearanceRegionAnchor(region,(-.4,.2,-.4),(.4,.2,.4),PROOF)
        result = run(region_anchors=(anchor,))
        report = next(r for r in result.views[0].regions if r.region==region)
        self.assertEqual("unknown",report.color_status)
        self.assertEqual(0,report.visible_samples)

    def test_unknown_lighting_abstains_and_keeps_raw_residual(self):
        views,inputs,mesh = fixture(True)
        result = analyze_appearance(views,inputs,surface=mesh,
            view_settings={key:AppearanceViewSettings("scene-linear","lit") for key in inputs})
        self.assertTrue(any(p.raw_delta and p.raw_delta>.1 for pair in result.pairs for p in pair.pixels))
        self.assertTrue(all(r.color_status=="unknown" for v in result.views for r in v.regions))

    def test_failed_upstream_stays_failed(self):
        views,inputs,mesh = fixture()
        evidence = Evidence("geometry-evidence","observation","Empty native geometry.",measurements=(Measurement("occupied",0,"voxel"),))
        finding = Finding("empty","geometry.empty","geometry","error","fail","Empty native geometry.",evidence=(evidence,))
        report = DiagnosticReport("failed-geometry",views,(EngineVersion("test","1"),),
            DiagnosticPolicy("test","1","b"*64,("geometry.empty",)),DiagnosticResolution(16,16), (finding,))
        result = analyze_appearance(views,inputs,surface=mesh,upstream_reports=(report,))
        self.assertEqual("fail",result.report.verification_status)
        self.assertEqual((report,),result.upstream_reports)

    def test_cancel_and_sample_budget_produce_partial_unknown(self):
        self.assertEqual("cancelled",run(cancel=lambda:True).report.completion)
        views,inputs,mesh = fixture()
        result = analyze_appearance(views,inputs,surface=mesh,policy=AppearancePolicy(max_samples=1))
        self.assertEqual("partial",result.report.completion)
        self.assertEqual("unknown",result.report.verification_status)

    def test_ray_work_exhaustion_returns_partial_not_an_exception(self):
        views,inputs,mesh = fixture()
        result = analyze_appearance(views,inputs,surface=mesh,policy=AppearancePolicy(max_work=1000))
        self.assertEqual("partial",result.report.completion)
        self.assertLessEqual(result.provenance.work_units,1000)

    def test_mock_identity_claims_are_called_but_never_qualified(self):
        from tests.test_appearance_semantics import FixtureAnalyzer
        analyzer = FixtureAnalyzer()
        result = run(vision_analyzer=analyzer)
        self.assertEqual(1,len(analyzer.calls))
        self.assertEqual("complete",result.semantic.state)
        self.assertEqual("unknown",result.identity_status)
        self.assertTrue(all(image.sha256 != image.source.sha256 for image in result.semantic.request.images))
        pair = result.semantic.request.pairs[0]
        self.assertEqual(result.report.view_set.views[0].image.sha256,pair.target_image_sha256)

    def test_dependency_invalidation_includes_source_policy_and_model(self):
        result = run()
        self.assertFalse(result.is_stale(result.report.view_set))
        self.assertTrue(result.is_stale(result.report.view_set,policy=AppearancePolicy(color_tolerance=.1)))
        self.assertTrue(result.is_stale(result.report.view_set,source_sha256="f"*64))
        self.assertTrue(result.is_stale(result.report.view_set,semantic_dependency="c"*64))

    def test_mismatched_image_and_mesh_bindings_do_not_compare(self):
        views,inputs,mesh = fixture()
        wrong = replace(inputs["target"].image,source_sha256="f"*64)
        result = analyze_appearance(views,{**inputs,"target":ViewInput(wrong)},surface=mesh)
        self.assertEqual("fail",result.report.verification_status)
        self.assertFalse(any(p.target_view_id=="target" for p in result.pairs))
        result = analyze_appearance(views,inputs,surface=replace(mesh,binding_sha256="e"*64))
        self.assertFalse(result.pairs)
        self.assertEqual("fail",result.report.verification_status)


if __name__ == "__main__":
    unittest.main()
