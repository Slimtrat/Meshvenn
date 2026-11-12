"""Adversarial D4 regressions using actual buffers and triangle visibility."""
from __future__ import annotations

import unittest

from core.appearance_diagnostics.engine import analyze_appearance
from core.appearance_diagnostics.models import AppearancePairResult, AppearanceRegionResult, AppearanceResult
from core.appearance_diagnostics.policy import AppearancePolicy, AppearanceViewSettings
from core.appearance_diagnostics.semantic_models import SemanticAnalyzerMetadata, SemanticResponse
from core.appearance_diagnostics.surface import SurfaceMesh
from core.diagnostic_contracts import (ArtifactReference, CameraDeclaration, CanonicalReference,
    EngineVersion, Region, ViewRevision, ViewSetRevision)
from core.diagnostics_preflight import RasterInput, ViewInput
from core.geometry_diagnostics.models import MaskArtifact
from core.image_mask import BinaryMask
from core.projection_alignment import ProjectionAlignment


PROOF = ArtifactReference("analytic-conservative-evidence", "a"*64, "application/json")
SETTINGS = AppearanceViewSettings("scene-linear", "albedo", 1., True, PROOF)


def fixture(*, checkerboard=False):
    """A planar source with an independently changed high-frequency texture.

    The central 8x8 patch agrees. Elsewhere the two actual input colors differ;
    their finite source-texel footprints are deliberately unresolved after the
    reference's small registration shift, so those colors must stay unknown.
    """
    inputs, views = {}, []
    for name in ("target", "reference"):
        rgba = []
        for y in range(32):
            for x in range(32):
                inside = 4 <= x < 28 and 4 <= y < 28
                rgb = (.2, .55, .4)
                if checkerboard and not (12 <= x < 20 and 12 <= y < 20):
                    colors = ((.8,.1,.1),(.1,.8,.1)) if name == "target" else ((.1,.1,.8),(.8,.8,.1))
                    rgb = colors[(x+y) % 2]
                rgba.extend((*rgb, 1.) if inside else (0.,0.,0.,0.))
        raster = RasterInput.from_pixels(32,32,rgba)
        inputs[name] = ViewInput(raster)
        alignment = ProjectionAlignment(.005,0.,1.) if checkerboard and name == "reference" else ProjectionAlignment()
        views.append(ViewRevision(name,1,raster.content_reference(),None,
            CameraDeclaration("orthographic",0.,0.,False,True,PROOF),alignment,
            role="reference" if name == "reference" else "observation"))
    revision = ViewSetRevision("conservative-appearance",1,tuple(views),
        CanonicalReference("accepted",1,views[1].image,True,("reference",),PROOF))
    surface = SurfaceMesh(((-.8,0.,-.8),(.8,0.,-.8),(.8,0.,.8),(-.8,0.,.8)),
                          ((0,1,2),(0,2,3)),PROOF)
    return revision,inputs,surface


def analyze(*, checkerboard=False, analyzer=None, cancel=None):
    revision, inputs, surface = fixture(checkerboard=checkerboard)
    return analyze_appearance(revision,inputs,surface=surface,
        view_settings={key:SETTINGS for key in inputs},
        policy=AppearancePolicy(sampling_size=32,require_identity=False),
        vision_analyzer=analyzer,cancel=cancel)


class LateCancelAnalyzer:
    """Transport cancellation fixture; no identity model is qualified here."""
    model = EngineVersion("test.late_cancel_model","adapter-contract-only")

    def __init__(self):
        self.cancelled = False

    def metadata(self):
        return SemanticAnalyzerMetadata(EngineVersion("test.late_cancel_adapter","1"),self.model)

    def analyze(self, request, *, timeout_seconds, cancel=None):
        self.cancelled = True
        return SemanticResponse(request.dependency_fingerprint,self.model,())


class AppearanceConservativeTests(unittest.TestCase):
    def test_unresolved_majority_cannot_pass_from_a_small_matching_color_patch(self):
        result = analyze(checkerboard=True)
        self.assertEqual(result.report.completion,"complete")
        self.assertEqual(result.report.verification_status,"unknown")
        self.assertEqual(len(result.views),2)
        for view in result.views:
            region = next(r for r in view.regions if r.region.label == "observed-view")
            self.assertEqual(region.coverage_status,"pass")
            self.assertEqual(region.color_status,"unknown")
            self.assertEqual(region.visible_samples,region.expected_samples)
            self.assertGreater(region.comparable_samples,8)
            self.assertLess(region.comparable_samples,region.expected_samples*.2)
            self.assertGreater(sum(view.unknown_mask.values),region.expected_samples*.8)
            self.assertEqual(region.changed_samples,0)

    def test_cancellation_after_analyzer_response_retains_evidence_without_pass(self):
        analyzer = LateCancelAnalyzer()
        result = analyze(analyzer=analyzer,cancel=lambda:analyzer.cancelled)
        self.assertTrue(analyzer.cancelled)
        self.assertEqual(result.report.completion,"cancelled")
        self.assertEqual(result.report.verification_status,"unknown")
        self.assertEqual(result.semantic.state,"cancelled")
        self.assertTrue(result.semantic.raw_response_json)
        self.assertTrue(result.semantic.raw_response_sha256)
        self.assertEqual(len(result.pairs),2)
        self.assertEqual(len(result.views),2)
        self.assertTrue(all(sum(view.comparable_mask.values) for view in result.views))
        self.assertEqual(AppearanceResult.from_json(result.to_json()),result)

    def test_empty_region_cannot_claim_resolved_pass(self):
        with self.assertRaises(ValueError):
            AppearanceRegionResult(Region("target","unresolved"),"pass","pass",0,0,0,0,None,
                                   "No measured support.",())

    def test_unresolved_pair_pixels_cannot_disappear_from_unknown_mask(self):
        zero = MaskArtifact.from_mask(BinaryMask(1,1,b"\x00"))
        one = MaskArtifact.from_mask(BinaryMask(1,1,b"\x01"))
        with self.assertRaises(ValueError):
            AppearancePairResult("pair-target-reference","target","reference","target",1,1,(),
                one,one,zero,zero,zero,None,None,"accepted_design")


if __name__ == "__main__":
    unittest.main()
