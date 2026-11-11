from __future__ import annotations

import hashlib
import math
import struct
import tempfile
import unittest
import zlib
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from core.diagnostic_contracts import (
    ArtifactReference, CameraDeclaration, CanonicalReference, ContentReference,
    DiagnosticReport, ViewRevision, ViewSetRevision,
)
from core.diagnostics_preflight import (
    AlignmentAnchor, PreflightPolicy, RasterInput, ViewInput,
    accept_alignment, analyze_preflight,
)
from core.image_mask import BinaryMask
from core.projection_alignment import ProjectionAlignment


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def mask(size=96, asymmetric=True):
    return BinaryMask(size, size, bytes(int(
        (0.34 < x/(size-1) < 0.65 and .2 < y/(size-1) < .75) or
        (asymmetric and .65 < x/(size-1) < .76 and .52 < y/(size-1) < .65))
        for y in range(size) for x in range(size)))


def raster(subject: BinaryMask, *, color=(.2, .4, .8), opaque=False) -> RasterInput:
    return RasterInput.from_pixels(subject.width, subject.height,
                                  tuple(v for inside in subject.values for v in
                                        (*color, 1. if (inside or opaque) else 0.)))


def source(subject: BinaryMask) -> ViewInput:
    image = raster(subject)
    segmentation = RasterInput.from_pixels(subject.width, subject.height,
                                            tuple(v for inside in subject.values for v in (inside, inside, inside, 1.)))
    return ViewInput(image, segmentation)


def fixture(observed=None, reference=None, camera=None):
    reference = reference or mask()
    observed = observed or reference
    evidence = ArtifactReference("camera-proof", digest(b"known-render-camera"), "application/json")
    camera = camera or CameraDeclaration("orthographic", 0., 0., verified=True, verification_evidence=evidence)
    data = {"front": source(observed), "ref-front": source(reference)}
    views = tuple(ViewRevision(name, 1, item.image.content_reference(), item.mask.content_reference(), camera,
                               role="reference" if name.startswith("ref") else "observation")
                  for name, item in data.items())
    canonical = CanonicalReference("canonical", 1, data["ref-front"].image.content_reference(),
                                   True, ("ref-front",), validation_evidence=evidence)
    view_set = ViewSetRevision("test", 1, views, canonical)
    anchors = (AlignmentAnchor("front", "ref-front", digest(b"independent-reference")),)
    policy = PreflightPolicy(required_cameras=((0., 0.),))
    return view_set, data, anchors, policy


def codes(result):
    return {finding.code: finding.status for finding in result.report.findings}


def png(subject: BinaryMask, *, filtering=0):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = []
    prior = bytes(subject.width * 4)
    for y in reversed(range(subject.height)):
        row = bytes(v for x in range(subject.width) for v in (255, 255, 255, 255 * subject.values[y * subject.width + x]))
        if filtering == 1:
            filtered = bytes((value - (row[i-4] if i >= 4 else 0)) & 255 for i, value in enumerate(row))
        elif filtering == 2:
            filtered = bytes((value - prior[i]) & 255 for i, value in enumerate(row))
        else:
            filtered = row
        rows.append(bytes((filtering,)) + filtered)
        prior = row
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", subject.width, subject.height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


class PreflightTests(unittest.TestCase):
    def test_healthy_intentional_asymmetry_is_unchanged_and_report_roundtrips(self):
        view_set, inputs, anchors, policy = fixture()
        original = inputs["front"]
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(result.proposals, ())
        self.assertEqual(codes(result)["alignment.within_tolerance"], "pass")
        self.assertEqual(result.report.verification_status, "pass")
        self.assertIs(inputs["front"], original)
        self.assertEqual(DiagnosticReport.from_json(result.report.to_json()), result.report)

    def test_shift_improves_bounded_reference_match_and_shared_certificate(self):
        original = mask()
        moved = ProjectionAlignment(offset_u=.08, offset_v=-.04).align_mask(original)
        view_set, inputs, anchors, policy = fixture(moved, original)
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(len(result.proposals), 1)
        proposal = result.proposals[0]
        self.assertGreaterEqual(proposal.after_iou, .97)
        self.assertGreater(proposal.after_iou, proposal.before_iou + .05)
        self.assertLessEqual(abs(proposal.alignment.offset_u), .15)
        accepted = accept_alignment(proposal, result, view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(accepted.color_transform_sha256, accepted.mask_transform_sha256)
        self.assertIs(accepted.source, inputs["front"])
        for y in range(96):
            for x in range(96):
                self.assertEqual(accepted.color_at(x/95, y/95)[3] > .1, accepted.aligned_mask.get(x, y))

    def test_uniform_scale_improves_without_axis_warp(self):
        original = mask(192)
        smaller = ProjectionAlignment(scale=.9).align_mask(original)
        view_set, inputs, anchors, policy = fixture(smaller, original)
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(len(result.proposals), 1)
        self.assertGreater(result.proposals[0].alignment.scale, 1)
        self.assertGreaterEqual(result.proposals[0].after_iou, .97)

    def test_real_proportion_difference_abstains(self):
        original = mask()
        changed = BinaryMask(96, 96, bytes(int(.34 < x/95 < .72 and .2 < y/95 < .75) for y in range(96) for x in range(96)))
        view_set, inputs, anchors, policy = fixture(changed, original)
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertFalse(result.proposals)
        self.assertEqual(codes(result)["alignment.shape_mismatch"], "unknown")
        self.assertNotIn("geometry.cross_view_conflict", codes(result))

    def test_mirror_is_not_a_registration_candidate(self):
        original = mask()
        view_set, inputs, anchors, policy = fixture(original.flipped_x(), original)
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertFalse(result.proposals)
        self.assertEqual(codes(result)["alignment.shape_mismatch"], "unknown")

    def test_empty_mask_and_alpha_are_preparation_defects(self):
        empty = BinaryMask(96, 96, bytes(96*96))
        view_set, inputs, anchors, policy = fixture(empty)
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(codes(result)["input.empty_mask"], "fail")
        self.assertEqual(codes(result)["input.empty_alpha"], "fail")
        self.assertFalse(result.proposals)

    def test_edge_contact_does_not_propose_clipping_alignment(self):
        cropped = BinaryMask(96, 96, bytes(int(x < 42 and 20 < y < 70) for y in range(96) for x in range(96)))
        view_set, inputs, anchors, policy = fixture(cropped)
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(codes(result)["input.subject_truncated"], "fail")
        self.assertFalse(result.proposals)

    def test_alpha_mask_mismatch_and_opaque_color(self):
        view_set, inputs, anchors, policy = fixture()
        moved = ProjectionAlignment(offset_u=.1).align_mask(mask())
        inputs["front"] = ViewInput(raster(moved), inputs["front"].mask)
        front = replace(view_set.views[0], image=inputs["front"].image.content_reference())
        view_set = replace(view_set, views=(front, view_set.views[1]))
        self.assertEqual(codes(analyze_preflight(view_set, inputs, anchors=anchors, policy=policy))["input.alpha_mask_mismatch"], "fail")
        inputs["front"] = ViewInput(raster(mask(), opaque=True), inputs["front"].mask)
        view_set = replace(view_set, views=(replace(front, image=inputs["front"].image.content_reference()), view_set.views[1]))
        self.assertNotIn("input.alpha_mask_mismatch", codes(analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)))

    def test_nonfinite_invalid_buffer_dimensions_and_wrong_source_hash(self):
        for bad in (replace(raster(mask()), rgba=(math.nan,) + raster(mask()).rgba[1:]),
                    replace(raster(mask()), rgba=(0.,)),
                    replace(raster(mask()), source_sha256=digest(b"wrong"))):
            view_set, inputs, anchors, policy = fixture()
            inputs["front"] = replace(inputs["front"], image=bad)
            result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
            self.assertTrue({"input.nonfinite", "input.dimension_mismatch", "input.hash_mismatch"} & codes(result).keys())
            self.assertFalse(result.proposals)

    def test_generated_camera_declaration_is_unknown_and_perspective_unsupported(self):
        for camera, code in ((CameraDeclaration("orthographic", 0., 0.), "camera.unverified"),
                             (CameraDeclaration("perspective", 0., 0.), "camera.unsupported")):
            view_set, inputs, anchors, policy = fixture(camera=camera)
            view_set = replace(view_set, views=tuple(replace(v, origin="generated") for v in view_set.views))
            result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
            self.assertIn(code, codes(result))
            self.assertFalse(result.proposals)

    def test_reference_coverage_does_not_supply_missing_observation(self):
        view_set, inputs, anchors, policy = fixture()
        policy = replace(policy, required_cameras=((0., 0.), (90., 0.)))
        reference = replace(view_set.views[1], camera=replace(view_set.views[1].camera, azimuth_degrees=90.))
        view_set = replace(view_set, views=(view_set.views[0], reference))
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(codes(result)["coverage.insufficient"], "fail")

    def test_missing_independent_reference_is_unknown(self):
        view_set, inputs, anchors, policy = fixture()
        result = analyze_preflight(view_set, inputs, policy=policy)
        self.assertFalse(result.proposals)
        self.assertEqual(codes(result)["alignment.reference_missing"], "unknown")
        self.assertEqual(result.report.verification_status, "unknown")

    def test_acceptance_rejects_stale_policy_and_tampered_pixels(self):
        original = mask()
        view_set, inputs, anchors, policy = fixture(ProjectionAlignment(offset_u=.08).align_mask(original), original)
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        proposal = result.proposals[0]
        with self.assertRaises(ValueError):
            accept_alignment(proposal, result, view_set, inputs, anchors=anchors, policy=replace(policy, max_offset=.14))
        tampered = dict(inputs)
        image = tampered["front"].image
        tampered["front"] = replace(tampered["front"], image=replace(image, rgba=(.9,) + image.rgba[1:]))
        with self.assertRaises(ValueError):
            accept_alignment(proposal, result, view_set, tampered, anchors=anchors, policy=policy)

    def test_permutation_preserves_findings_and_dependency_fingerprint(self):
        view_set, inputs, anchors, policy = fixture()
        first = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        second = analyze_preflight(replace(view_set, views=tuple(reversed(view_set.views)), input_order=tuple(reversed(view_set.input_order))),
                                   dict(reversed(tuple(inputs.items()))), anchors=anchors, policy=policy)
        self.assertEqual(first.report.dependency_fingerprint, second.report.dependency_fingerprint)
        self.assertEqual(first.report.findings, second.report.findings)

    def test_png_crc_filters_orientation_and_malformed_data(self):
        subject = mask(32)
        for filtering in (0, 1, 2):
            encoded = png(subject, filtering=filtering)
            image = RasterInput.from_png_bytes(encoded)
            self.assertFalse(image.error)
            self.assertEqual(tuple(int(image.rgba[i] > .1) for i in range(3, len(image.rgba), 4)), tuple(subject.values))
            self.assertEqual(image.source_sha256, digest(encoded))
        encoded = png(subject)
        corrupted = encoded[:45] + bytes((encoded[45] ^ 1,)) + encoded[46:]
        self.assertIn("checksum", RasterInput.from_png_bytes(corrupted).error)
        self.assertTrue(RasterInput.from_png_bytes(encoded[:-2]).error)
        self.assertTrue(RasterInput.from_png_bytes(b"JPEG bytes").unsupported)

    def test_encoded_malformed_source_becomes_actionable_finding(self):
        view_set, inputs, anchors, policy = fixture()
        inputs["front"] = replace(inputs["front"], image=RasterInput.from_png_bytes(png(mask())[:-2]))
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(codes(result)["input.unreadable"], "fail")
        self.assertFalse(result.proposals)

    def test_actual_empty_or_corrupt_file_with_unknown_dimensions_is_failed(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "source.png"
            for payload in (b"", png(mask())[:-2]):
                path.write_bytes(payload)
                view_set, inputs, anchors, policy = fixture()
                broken = RasterInput.from_path(path)
                self.assertIsNone(broken.width)
                inputs["front"] = replace(inputs["front"], image=broken)
                front = replace(view_set.views[0], image=None)
                view_set = replace(view_set, views=(front, view_set.views[1]))
                result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
                self.assertEqual(codes(result)["input.unreadable"], "fail")
                self.assertNotIn("input.missing", codes(result))

    def test_opaque_without_segmentation_is_unknown_instead_of_invented_crop(self):
        view_set, inputs, anchors, policy = fixture()
        inputs["front"] = ViewInput(raster(mask(), opaque=True))
        front = replace(view_set.views[0], image=inputs["front"].image.content_reference(), mask=None)
        view_set = replace(view_set, views=(front, view_set.views[1]))
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(codes(result)["input.segmentation_missing"], "unknown")
        self.assertNotIn("input.subject_truncated", codes(result))

    def test_duplicate_color_different_cameras_is_reviewable_unknown(self):
        view_set, inputs, anchors, policy = fixture()
        second = replace(view_set.views[1], role="observation",
                         camera=replace(view_set.views[1].camera, azimuth_degrees=90.))
        view_set = replace(view_set, views=(view_set.views[0], second))
        result = analyze_preflight(view_set, inputs, policy=policy)
        self.assertEqual(codes(result)["input.duplicate"], "unknown")
        duplicate = next(f for f in result.report.findings if f.code == "input.duplicate")
        self.assertFalse(duplicate.required)

    def test_large_raster_search_is_bounded_and_winner_uses_native_grid(self):
        from core.diagnostics_preflight import registration
        original = mask(256)
        shifted = ProjectionAlignment(offset_u=.08).align_mask(original)
        with patch.object(registration, "_fit_grid", wraps=registration._fit_grid) as search:
            fit = registration.fit_similarity(shifted, original, min_scale=.8, max_scale=1.25, max_offset=.15)
        self.assertIsNotNone(fit)
        self.assertLessEqual(max(search.call_args.args[0].width, search.call_args.args[0].height), 128)
        self.assertEqual(fit[2], registration.mask_iou(fit[0].align_mask(shifted), original))

    def test_png_resource_budget_fails_before_allocation(self):
        encoded = png(mask(8))
        header = struct.pack(">IIBBBBB", 4096, 4096, 8, 6, 0, 0, 0)
        ihdr = struct.pack(">I", len(header)) + b"IHDR" + header + struct.pack(">I", zlib.crc32(b"IHDR" + header) & 0xffffffff)
        oversized = encoded[:8] + ihdr + encoded[33:]
        result = RasterInput.from_png_bytes(oversized)
        self.assertIn("pixel budget", result.error)
        self.assertFalse(result.rgba)

    def test_alignment_cannot_erase_a_thin_original_component_to_improve_iou(self):
        n = 96
        reference = BinaryMask(n, n, bytes(int((.28 < x/95 < .7 and .2 < y/95 < .4) or
                                               (.28 < x/95 < .43 and .2 < y/95 < .8))
                                           for y in range(n) for x in range(n)))
        enlarged = ProjectionAlignment(scale=1.2).align_mask(reference)
        values = bytearray(enlarged.values)
        for y in range(45, 57):
            values[y*n+50] = 1
        observation = BinaryMask(n, n, bytes(values))
        view_set, inputs, anchors, policy = fixture(observation, reference)
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertFalse(result.proposals)
        self.assertEqual(codes(result)["alignment.shape_mismatch"], "unknown")
        from core.diagnostics_preflight.registration import _retains_components
        disappearing = ProjectionAlignment(-.001712, -.001712, .837359943977591)
        self.assertFalse(_retains_components(observation, reference, disappearing, disappearing.align_mask(observation)))

    def test_reference_derived_from_target_is_not_independent(self):
        original = mask()
        view_set, inputs, anchors, policy = fixture(ProjectionAlignment(offset_u=.08).align_mask(original), original)
        reference = replace(view_set.views[1], origin="derived", derived_from=(view_set.views[0].image.sha256,))
        view_set = replace(view_set, views=(view_set.views[0], reference))
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertFalse(result.proposals)
        self.assertEqual(codes(result)["alignment.reference_missing"], "unknown")

    def test_png_illegal_header_and_duplicate_palette_are_malformed_not_unsupported(self):
        encoded = png(mask(8))
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        for depth, color, interlace in ((9,6,0), (8,1,0), (8,6,2)):
            header = struct.pack(">IIBBBBB", 8, 8, depth, color, 0, 0, interlace)
            image = RasterInput.from_png_bytes(encoded[:8]+chunk(b"IHDR", header)+encoded[33:])
            self.assertTrue(image.error)
            self.assertFalse(image.unsupported)
        palette = chunk(b"PLTE", b"\0\0\0")
        image = RasterInput.from_png_bytes(encoded[:33]+palette+palette+encoded[33:])
        self.assertTrue(image.error)
        self.assertFalse(image.unsupported)

    def test_oversized_host_dimensions_remain_actionable_without_hash_overflow(self):
        view_set, inputs, anchors, policy = fixture()
        inputs["front"] = replace(inputs["front"], image=RasterInput.from_pixels(2**63, 1, ()))
        result = analyze_preflight(view_set, inputs, anchors=anchors, policy=policy)
        self.assertEqual(codes(result)["input.unreadable"], "fail")


if __name__ == "__main__":
    unittest.main()
