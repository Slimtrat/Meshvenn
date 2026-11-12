"""Measured original-image color residuals; visibility remains separate evidence."""
from __future__ import annotations

import math
import statistics

from ..diagnostic_contracts import Region
from ..diagnostics_preflight.registration import mask_from_input
from ..geometry_diagnostics.metrics import _bounds, _components
from ..geometry_diagnostics.models import MaskArtifact
from ..geometry_diagnostics.projection import check_budget
from ..image_mask import BinaryMask
from .models import (AppearancePairResult, AppearancePixel, AppearanceRegionResult,
                     AppearanceViewResult)
from .sampling import foreground, sample_color


def mask_artifact(width, height, values):
    return MaskArtifact.from_mask(BinaryMask(width, height, bytes(values)))


def difference(a, b):
    return max(abs(x-y) for x,y in zip(a,b))


def compare_pair(mapping, *, target_id, reference_id, inputs, settings, subject_masks,
                 policy, deadline, cancel, color_cache):
    source_id = mapping.target_view_id
    counterpart = reference_id if source_id == target_id else target_id
    width,height = mapping.width,mapping.height
    expected, visible, comparable, changed = (bytearray(width*height) for _ in range(4))
    pixels, ratios = [], []

    def color(view_id, uv):
        key = (view_id, uv)
        if key not in color_cache:
            color_cache[key] = sample_color(inputs[view_id], uv, settings[view_id],
                min_alpha=policy.min_alpha, boundary_tolerance=policy.color_tolerance,
                subject_mask=subject_masks[view_id])
        return color_cache[key]

    for point in mapping.pixels:
        if len(pixels) % 256 == 0:
            check_budget(deadline, cancel)
        index = point.y*width+point.x
        if not foreground(inputs[source_id], point.target_original_uv, subject_mask=subject_masks[source_id]):
            continue
        expected[index] = 1
        ref = next((r for r in point.references if r.view_id == counterpart), None)
        target_uv = point.target_original_uv if source_id == target_id else ref.original_uv if ref else None
        reference_uv = point.target_original_uv if source_id == reference_id else ref.original_uv if ref else None
        visibility = point.state if point.state != "visible" else ref.state if ref else "unknown"
        state, reason = "correspondence_unknown", point.reason if point.state != "visible" else (
            ref.reason if ref else "No calibrated counterpart correspondence is available.")
        target_sample = reference_sample = None
        raw_delta = corrected_delta = None
        if point.state == "visible" and ref is not None and ref.visible:
            visible[index] = 1
            target_sample, reference_sample = color(target_id,target_uv), color(reference_id,reference_uv)
            if target_sample.raw_rgb is not None and reference_sample.raw_rgb is not None:
                raw_delta = difference(target_sample.raw_rgb,reference_sample.raw_rgb)
                ratios.extend(a/b for a,b in zip(target_sample.raw_rgb,reference_sample.raw_rgb) if b > .02)
            if target_sample.state == reference_sample.state == "comparable":
                comparable[index] = 1
                corrected_delta = difference(target_sample.rgb,reference_sample.rgb)
                changed[index] = int(corrected_delta > policy.color_tolerance)
                state = "different" if changed[index] else "consistent"
                reason = "Visible scene-linear colors compared under declared producer photometry."
            else:
                state = ("lighting_unknown" if any(s.state == "uncontrolled" for s in (target_sample,reference_sample))
                         else "sampling_unknown")
                reason = "; ".join(sorted({target_sample.reason,reference_sample.reason}))
        pixels.append(AppearancePixel(point.x,point.y,target_uv,reference_uv,point.triangle_index,
            visibility,state,reason,
            target_sample.raw_rgb if target_sample else None,
            reference_sample.raw_rgb if reference_sample else None,
            target_sample.rgb if target_sample else None,
            reference_sample.rgb if reference_sample else None,raw_delta,corrected_delta))
    fitted_gain = statistics.median(ratios) if len(ratios) >= policy.min_region_samples else None
    fit_residual = None
    if fitted_gain is not None and .25 <= fitted_gain <= 4:
        residuals = [difference(pixel.target_raw_rgb, tuple(fitted_gain*c for c in pixel.reference_raw_rgb))
                     for pixel in pixels if pixel.target_raw_rgb is not None and pixel.reference_raw_rgb is not None]
        fit_residual = sum(residuals)/len(residuals) if residuals else None
    unknown = bytes(int(e and not c) for e,c in zip(expected,comparable))
    pair_id = "pair-"+source_id+"-"+counterpart
    return AppearancePairResult(pair_id,target_id,reference_id,source_id,width,height,tuple(pixels),
        mask_artifact(width,height,expected),mask_artifact(width,height,visible),
        mask_artifact(width,height,comparable),mask_artifact(width,height,changed),
        mask_artifact(width,height,unknown),fitted_gain,fit_residual,"accepted_design")


def canonical_conflicts(mapping, pairs, tolerance):
    """Distinct accepted reference colors can conflict at the same surface point.

    This diagnoses the reference group, not the observation's fault. It compares
    already visibility-qualified samples and never mirrors opposite surfaces.
    """
    if len(pairs) < 2:
        return ()
    by_pixel = {}
    for pair in pairs:
        for pixel in pair.pixels:
            if pixel.state in ("consistent","different") and pixel.reference_rgb is not None:
                by_pixel.setdefault((pixel.x,pixel.y),[]).append((pair.reference_view_id,pixel.reference_rgb))
    return tuple(sorted({name for samples in by_pixel.values() for name,color in samples
                         if any(difference(color,other) > tolerance for _,other in samples)}))


def aggregate_view(mapping, pairs, *, data, role, settings, requested_regions, region_anchors=(), policy, deadline, cancel):
    width,height = mapping.width,mapping.height
    length = width*height
    expected,visible,comparable,changed = (bytearray(length) for _ in range(4))
    for pair in pairs:
        for target,mask in ((expected,pair.expected_mask),(visible,pair.visible_mask),
                            (comparable,pair.comparable_mask),(changed,pair.changed_mask)):
            for index,value in enumerate(mask.values):
                target[index] |= value
    # Even with no supported references, retain the original source support.
    if not pairs:
        subject_mask = mask_from_input(data,.1,.5)
        for point in mapping.pixels:
            expected[point.y*width+point.x] = foreground(data,point.target_original_uv,subject_mask=subject_mask)
    regions = [Region(mapping.target_view_id,"observed-view",(0.,0.,1.,1.))]
    regions.extend(r for r in requested_regions if r.view_id == mapping.target_view_id)
    regions = tuple(dict.fromkeys(regions))
    reports = []
    for region in regions:
        check_budget(deadline,cancel)
        if region.bounds is None:
            reports.append(AppearanceRegionResult(region,"unknown","unknown",0,0,0,0,None,
                "The requested feature has no original-image bounds; the whole frame cannot substitute for it.",()))
            continue
        bounds = region.bounds or (0.,0.,1.,1.)
        selected = [i for i,value in enumerate(expected) if value and
                    bounds[0] <= ((i%width)/(width-1) if width > 1 else .5) <= bounds[2] and
                    bounds[1] <= ((i//width)/(height-1) if height > 1 else .5) <= bounds[3]]
        anchor = next((a for a in region_anchors if a.region == region), None)
        points = {p.y*width+p.x: p for p in mapping.pixels} if anchor else {}
        supported_indices = [i for i in selected if anchor is None or
            anchor.contains(points[i].point3d, points[i].triangle_index)]
        counts = [sum(values[i] for i in supported_indices) for values in (visible,comparable,changed)]
        visible_count,comparable_count,changed_count = counts
        coverage = visible_count/len(selected) if selected else None
        extent = (min(max(i%width for i in selected)-min(i%width for i in selected)+1,
                      max(i//width for i in selected)-min(i//width for i in selected)+1) if selected else 0)
        supported = len(selected) >= policy.min_region_samples and extent >= policy.min_region_extent
        coverage_status = "pass" if supported and coverage >= policy.min_coverage else "unknown"
        color_status = "unknown"
        if supported and comparable_count >= policy.min_region_samples:
            fraction = changed_count/comparable_count
            color_status = ("fail" if changed_count >= policy.min_changed_pixels and fraction > policy.max_changed_fraction
                            else "pass" if comparable_count/len(selected) >= policy.min_coverage and
                            (anchor is None or coverage_status == "pass") else "unknown")
        reason = ("Visible measured samples support the declared color comparison; unresolved samples remain in the unknown mask."
                  if color_status != "unknown" else "The region lacks resolved, calibrated and visible color support.")
        reports.append(AppearanceRegionResult(region,coverage_status,color_status,len(selected),visible_count,
            comparable_count,changed_count,coverage,reason,tuple(sorted({
                pair.reference_view_id if pair.target_view_id == mapping.target_view_id else pair.target_view_id for pair in pairs}))))
    # A small localized loss cannot be hidden by a passing full-view mean.
    for index,component in enumerate(_components(bytes(changed),width,height,deadline,cancel)):
        if index >= policy.max_regions:
            reports.append(AppearanceRegionResult(Region(mapping.target_view_id,"unresolved-differences"),
                "unknown","unknown",0,0,0,0,None,"Localized difference count exceeds the declared region budget.",()))
            break
        bounds,extent = _bounds(component,width,height)
        reports.append(AppearanceRegionResult(Region(mapping.target_view_id,"visible-difference-"+str(index),bounds),
            "pass","fail" if len(component) >= policy.min_changed_pixels and min(extent) >= policy.min_region_extent else "unknown",len(component),len(component),
            len(component),len(component),1.,"Localized measured color residual, independent of global mean.",
            tuple(sorted({pair.target_view_id for pair in pairs}))))
    unknown = bytes(int(e and not c) for e,c in zip(expected,comparable))
    return AppearanceViewResult(mapping.target_view_id,role,width,height,
        tuple(pair.pair_id for pair in pairs),mask_artifact(width,height,expected),mask_artifact(width,height,visible),
        mask_artifact(width,height,comparable),mask_artifact(width,height,changed),mask_artifact(width,height,unknown),
        tuple(reports),tuple(sorted({p.triangle_index for p in mapping.pixels if p.state == "visible" and p.triangle_index is not None})),
        data.image.source_sha256,data.image.decoded_sha256,settings)
