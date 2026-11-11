"""Real existing INPUT/material consumers of a reproduced preflight alignment.

Run: blender --background --factory-startup --python-exit-code 1
     --python tests/blender_preflight_input_smoke.py
"""
from __future__ import annotations

import hashlib
import importlib
import math
import struct
import sys
import zlib
from dataclasses import replace
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def png(mask, *, segmentation=False):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = []
    for y in reversed(range(mask.height)):
        row = bytearray((0,))
        for x in range(mask.width):
            occupied = mask.get(x, y)
            row.extend((255 * occupied,) * 3 + (255,) if segmentation else (128, 96, 64, 255 * occupied))
        rows.append(bytes(row))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", mask.width, mask.height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def main():
    addon = importlib.import_module(ROOT.name)
    contracts = importlib.import_module(f"{ROOT.name}.core.diagnostic_contracts")
    preflight = importlib.import_module(f"{ROOT.name}.core.diagnostics_preflight")
    pipeline = importlib.import_module(f"{ROOT.name}.core.pipeline_contracts")
    inputs_module = importlib.import_module(f"{ROOT.name}.implementations.projection_images")
    sampling = importlib.import_module(f"{ROOT.name}.core.projected_material.sampling")
    BinaryMask = importlib.import_module(f"{ROOT.name}.core.image_mask").BinaryMask
    ProjectionAlignment = importlib.import_module(f"{ROOT.name}.core.projection_alignment").ProjectionAlignment
    addon.register()
    manual_image = None
    try:
        settings = bpy.context.scene.bpt_settings
        settings.projections.clear()
        first = settings.projections.add()
        first.name, first.azimuth, first.elevation = "Front", 0., 0.
        first.enabled = True
        second = settings.projections.add()
        second.name, second.azimuth, second.elevation = "Side", math.pi/2, 0.
        second.enabled = True
        manual_image = bpy.data.images.new("ManualUnboundControl", width=8, height=8, alpha=True)
        manual_pixels = [value for y in range(8) for x in range(8)
                         for value in (.3, .4, .5, float(1 < x < 6 and 1 < y < 6))]
        manual_image.pixels.foreach_set(manual_pixels)
        manual_image.update()
        second.image = manual_image
        legacy_alignment_smoke = importlib.import_module(
            f"{ROOT.name}.tests.blender_smoke_support.projection_alignment")
        legacy_alignment_smoke._validate_projection_alignment(ROOT.name, settings)
        original = BinaryMask(96, 96, bytes(int((.34 < x/95 < .65 and .2 < y/95 < .75) or
                                                (.65 < x/95 < .76 and .52 < y/95 < .65))
                                             for y in range(96) for x in range(96)))
        shifted = ProjectionAlignment(.08, -.04, 1).align_mask(original)
        rasters = {name: preflight.ViewInput(preflight.RasterInput.from_png_bytes(png(subject)),
                                            preflight.RasterInput.from_png_bytes(png(subject, segmentation=True)))
                   for name, subject in (("front", shifted), ("ref-front", original))}
        proof_hash = hashlib.sha256(b"independently-authored-orthographic-reference").hexdigest()
        proof = contracts.ArtifactReference("analytic-proof", proof_hash, "application/json")
        camera = contracts.CameraDeclaration("orthographic", 0, 0, verified=True, verification_evidence=proof)
        view_set = contracts.ViewSetRevision("consumer-smoke", 1, tuple(
            contracts.ViewRevision(name, 1, data.image.content_reference(), data.mask.content_reference(), camera,
                                   role="reference" if name.startswith("ref") else "observation", origin="rendered")
            for name, data in rasters.items()),
            contracts.CanonicalReference("identity", 1, rasters["ref-front"].image.content_reference(),
                                         validated=True, view_ids=("ref-front",), validation_evidence=proof))
        anchors = (preflight.AlignmentAnchor("front", "ref-front", proof_hash),)
        policy = preflight.PreflightPolicy(alpha_threshold=float(settings.alpha_threshold), required_cameras=((0., 0.),))
        result = preflight.analyze_preflight(view_set, rasters, anchors=anchors, policy=policy)
        assert len(result.proposals) == 1
        binding = inputs_module.ProjectionAlignmentBinding("Front", "front", result.proposals[0].proposal_id, "sRGB")
        request = inputs_module.PreflightProjectionRequest(result, view_set, rasters, (binding,), anchors, policy)
        implementation = inputs_module.ProjectionImagesImplementation()
        context = pipeline.PipelineContext(scene=bpy.context.scene, settings=settings, source=request)
        assert implementation.availability(context).available
        scene_before = tuple((p.name, p.image, p.azimuth, p.elevation, p.flip_x,
                              p.alignment_offset_u, p.alignment_offset_v, p.alignment_scale)
                             for p in settings.projections)
        actual = implementation.execute(context)
        assert actual.success, actual.message
        corrected, manual = actual.payload.views
        assert corrected.native_projection.mask is corrected.mask
        assert corrected.material_view.mask is corrected.mask
        assert corrected.material_view.alignment is corrected.alignment
        assert corrected.preflight.accepted.alignment is corrected.alignment
        assert tuple(corrected.material_view.image.pixels) == rasters["front"].image.rgba
        assert corrected.material_view.image.rgb_encoding == "sRGB"
        assert corrected.preflight.accepted.source is rasters["front"]
        metadata = actual.metadata["views"][0]["preflight"]
        assert metadata["certificate_sha256"] == metadata["color_transform_sha256"] == metadata["mask_transform_sha256"]
        assert metadata["source_image_sha256"] == view_set.views[0].image.sha256
        assert metadata["source_mask_sha256"] == view_set.views[0].mask.sha256
        assert metadata["decoded_image_sha256"] == rasters["front"].image.decoded_sha256
        assert actual.diagnostic_report == result.report
        assert actual.diagnostic_report is actual.payload.diagnostic_report
        assert manual.preflight is None and manual.alignment.is_identity
        assert manual.image_name == manual_image.name

        # Exercise the shipped material sampler, including real sRGB conversion,
        # at an interior mask pixel. Mask uses nearest, color keeps alpha-aware bilinear.
        point = next((x, y) for y in range(2, 94) for x in range(2, 94)
                     if all(corrected.mask.get(x+dx, y+dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)))
        u, v = point[0]/95, point[1]/95
        candidate = sampling._sample_source_view((4*u-2, 0., 4*v), (0., -1., 0.), corrected.material_view,
                                                width=4, depth=4, height=4, voxel_size=1., center_xy=True)
        assert candidate is not None
        expected = tuple(((value/255+.055)/1.055)**2.4 for value in (128, 96, 64))
        assert max(abs(a-b) for a, b in zip((candidate.red, candidate.green, candidate.blue), expected)) < 1e-7
        assert abs(candidate.alpha-1) < 1e-7

        # Every dependency rejection occurs before INPUT output/metadata publication.
        def rejected(changed_request):
            sentinel = object()
            trial = pipeline.PipelineContext(scene=bpy.context.scene, settings=settings,
                                             source=changed_request, metadata={"sentinel": "preserved"})
            trial.set_output(pipeline.PipelineStage.INPUT, sentinel)
            snapshot = dict(trial.metadata)
            failure = implementation.execute(trial)
            assert failure.failed and failure.payload is None, failure.message
            assert trial.get_output(pipeline.PipelineStage.INPUT) is sentinel
            assert trial.metadata == snapshot

        changed_inputs = dict(rasters)
        image = rasters["front"].image
        changed_inputs["front"] = replace(rasters["front"], image=replace(image, rgba=(.9,) + image.rgba[1:]))
        rejected(replace(request, inputs=changed_inputs))
        changed_inputs["front"] = replace(rasters["front"], image=replace(image, source_sha256="0"*64))
        rejected(replace(request, inputs=changed_inputs))
        rejected(replace(request, policy=replace(policy, max_offset=.14)))
        rejected(replace(request, bindings=(replace(binding, view_id="unknown"),)))
        rejected(replace(request, bindings=(replace(binding, proposal_id="unknown"),)))
        first.azimuth = .1
        rejected(request)
        first.azimuth = 0.
        first.alignment_offset_u = .01
        rejected(request)
        first.alignment_offset_u = 0.
        assert scene_before == tuple((p.name, p.image, p.azimuth, p.elevation, p.flip_x,
                                      p.alignment_offset_u, p.alignment_offset_v, p.alignment_scale)
                                     for p in settings.projections)
        # Without an explicit binding the historical scene source path still
        # ignores missing images and enforces its two-image minimum.
        legacy = implementation.execute(pipeline.PipelineContext(scene=bpy.context.scene, settings=settings))
        assert legacy.failed and legacy.diagnostic_report is None
        print("PREFLIGHT_INPUT_CONSUMERS_PASS: existing INPUT, material sRGB sampling, shared certificates, mixed manual path, stale rollback")
    finally:
        addon.unregister()
        if manual_image is not None:
            bpy.data.images.remove(manual_image, do_unlink=True)


if __name__ == "__main__":
    main()
