"""Exercise the pure explicit-binding validator without importing Blender."""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from core.diagnostics_preflight import analyze_preflight
from core.projection_alignment import ProjectionAlignment
from tests.test_diagnostics_preflight import fixture, mask


def load_binding_module():
    # Mount only this implementation leaf. Importing the add-on lifecycle would
    # correctly require bpy, while the request contract itself must stay pure.
    root = Path(__file__).resolve().parents[1]
    prefix = "_meshvenn_binding_test"
    for name in (prefix, prefix + ".implementations", prefix + ".implementations.projection_images"):
        namespace = types.ModuleType(name)
        namespace.__path__ = []
        sys.modules[name] = namespace
    for name, module in tuple(sys.modules.items()):
        if name == "core" or name.startswith("core."):
            sys.modules[prefix + "." + name] = module
    name = prefix + ".implementations.projection_images.preflight"
    spec = importlib.util.spec_from_file_location(name, root / "implementations/projection_images/preflight.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


binding_module = load_binding_module()
PreflightProjectionRequest = binding_module.PreflightProjectionRequest
ProjectionAlignmentBinding = binding_module.ProjectionAlignmentBinding


def request_fixture():
    original = mask()
    shifted = ProjectionAlignment(offset_u=.08).align_mask(original)
    view_set, inputs, anchors, policy = fixture(shifted, original)
    result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
    binding = ProjectionAlignmentBinding("Front", "front", result.proposals[0].proposal_id, "scene-linear")
    request = PreflightProjectionRequest(result, view_set, inputs, (binding,), anchors, policy)
    projection = SimpleNamespace(name="Front", enabled=True, image=None, azimuth=0., elevation=0.,
                                 flip_x=False, alignment_offset_u=0., alignment_offset_v=0., alignment_scale=1.)
    return request, projection


class PreflightProjectionBindingTests(unittest.TestCase):
    def test_immutable_explicit_binding_reproduces_acceptance(self):
        request, projection = request_fixture()
        copied = dict(request.inputs)
        reconstructed = replace(request, inputs=copied, bindings=list(request.bindings), anchors=list(request.anchors))
        copied.clear()
        self.assertEqual(len(reconstructed.inputs), 2)
        with self.assertRaises(TypeError):
            reconstructed.inputs["other"] = request.inputs["front"]
        accepted = reconstructed.certify((projection,), alpha_threshold=request.policy.alpha_threshold)
        self.assertEqual(accepted["Front"].accepted.source_image_sha256, request.view_set.views[0].image.sha256)
        self.assertEqual(accepted["Front"].accepted.source, request.inputs["front"])
        with self.assertRaises(TypeError):
            accepted["other"] = accepted["Front"]

    def test_duplicate_unknown_disabled_and_ambiguous_mappings_are_rejected(self):
        request, projection = request_fixture()
        for binding in (request.bindings[0], replace(request.bindings[0], projection_name="Other"),
                        replace(request.bindings[0], view_id="other")):
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                replace(request, bindings=(*request.bindings, binding))
        for projections in ((), (projection, projection), (SimpleNamespace(name="Front", enabled=False),)):
            with self.subTest(projections=projections), self.assertRaises(ValueError):
                request.certify(projections, alpha_threshold=request.policy.alpha_threshold)
        for binding in (replace(request.bindings[0], view_id="absent"),
                        replace(request.bindings[0], proposal_id="absent")):
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                replace(request, bindings=(binding,)).certify((projection,), alpha_threshold=request.policy.alpha_threshold)

    def test_changed_source_policy_camera_or_alignment_cannot_reuse_a_certificate(self):
        request, projection = request_fixture()
        inputs = dict(request.inputs)
        image = inputs["front"].image
        inputs["front"] = replace(inputs["front"], image=replace(image, rgba=(.9,) + image.rgba[1:]))
        for changed in (replace(request, inputs=inputs), replace(request, policy=replace(request.policy, max_offset=.14))):
            with self.subTest(changed=changed.policy), self.assertRaises(ValueError):
                changed.certify((projection,), alpha_threshold=request.policy.alpha_threshold)
        with self.assertRaises(ValueError):
            request.certify((projection,), alpha_threshold=.2)
        for change in ({"azimuth": .1}, {"elevation": .1}, {"flip_x": True}, {"alignment_offset_u": .01}):
            changed = SimpleNamespace(**{**vars(projection), **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                request.certify((changed,), alpha_threshold=request.policy.alpha_threshold)

    def test_caller_forged_proposal_is_reproduced_and_rejected(self):
        request, projection = request_fixture()
        forged = replace(request.result.proposals[0], alignment=ProjectionAlignment(.15, 0, 1))
        tampered = replace(request, result=replace(request.result, proposals=(forged,)))
        with self.assertRaises(ValueError):
            tampered.certify((projection,), alpha_threshold=request.policy.alpha_threshold)

    def test_supplied_report_findings_are_recomputed_before_consumers_receive_them(self):
        request, projection = request_fixture()
        passing = replace(request.result.report, findings=tuple(
            finding for finding in request.result.report.findings if finding.status == "pass"))
        self.assertEqual(passing.verification_status, "pass")
        tampered = replace(request, result=replace(request.result, report=passing))
        actual = tampered.certify((projection,), alpha_threshold=request.policy.alpha_threshold)
        self.assertEqual(actual["Front"].report.verification_status, "fail")
        self.assertEqual(actual["Front"].report, request.result.report)

    def test_color_encoding_must_be_declared_and_supported(self):
        with self.assertRaises(TypeError):
            ProjectionAlignmentBinding("Front", "front", "proposal")
        with self.assertRaises(ValueError):
            ProjectionAlignmentBinding("Front", "front", "proposal", "guess")


if __name__ == "__main__":
    unittest.main()
