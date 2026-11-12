"""Actual D4 masks and sampled colours; no decorative or corrected asset images."""
from __future__ import annotations

import re

from .authoring import png_rgba, sha256


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]","_",value)[:40] + "-" + sha256(value.encode())[:8]


def mask_overlay(view):
    pixels = bytearray()
    for expected,comparable,changed,unknown in zip(view.expected_mask.values,view.comparable_mask.values,
                                                 view.changed_mask.values,view.unknown_mask.values):
        colour = (220,45,60,255) if changed else (240,185,50,255) if unknown else \
                 (50,160,100,255) if comparable else (120,130,140,255) if expected else (250,250,250,255)
        pixels.extend(colour)
    return png_rgba(view.width,view.height,bytes(pixels))


def sample_image(pair, attribute, *, heat=False):
    data = bytearray(bytes((250,250,250,255)) * pair.width * pair.height)
    for sample in pair.pixels:
        value = getattr(sample,attribute)
        if value is None:
            continue
        colour = (int(255*min(1.,value)),0,0,255) if heat else \
                 tuple(max(0,min(255,int(channel*255+.5))) for channel in value) + (255,)
        index = (sample.y*pair.width+sample.x)*4
        data[index:index+4] = bytes(colour)
    return png_rgba(pair.width,pair.height,bytes(data))


def write_evidence(destination, result):
    artifacts = []
    for view in result.views:
        filename = "status-" + safe_name(view.view_id) + ".png"
        data = mask_overlay(view)
        (destination/filename).write_bytes(data)
        artifacts.append({"view_ids":[view.view_id],"path":filename,"sha256":sha256(data),"media_type":"image/png",
                          "kind":"actual_d4_status_masks","legend":"red changed; amber unknown; green comparable unchanged; grey expected without comparable support; white outside expected"})
    for pair in result.pairs:
        for attribute, suffix, heat in (("target_raw_rgb","target-raw-samples",False),
                                        ("reference_raw_rgb","reference-raw-samples",False),
                                        ("raw_delta","raw-delta",True),
                                        ("corrected_delta","declared-correction-delta",True)):
            filename = "pair-" + safe_name(pair.pair_id) + "-" + suffix + ".png"
            data = sample_image(pair,attribute,heat=heat)
            (destination/filename).write_bytes(data)
            artifacts.append({"view_ids":[pair.target_view_id,pair.reference_view_id],"pair_id":pair.pair_id,
                              "map_view_id":pair.map_view_id,"path":filename,"sha256":sha256(data),"media_type":"image/png",
                              "kind":"actual_d4_"+suffix,"heat_scale":"red=min(delta,1), no fitted display threshold" if heat else None,
                              "missing_values":"white denotes no measured value, not zero error"})
    return tuple(artifacts)


def raw_metrics(result):
    raw,corrected,visibility = [],[],{}
    pairs = []
    for pair in result.pairs:
        pair_raw,pair_corrected,states = [],[],{}
        for sample in pair.pixels:
            visibility[sample.visibility] = visibility.get(sample.visibility,0)+1
            states[sample.visibility] = states.get(sample.visibility,0)+1
            if sample.raw_delta is not None:
                raw.append(sample.raw_delta)
                pair_raw.append(sample.raw_delta)
            if sample.corrected_delta is not None:
                corrected.append(sample.corrected_delta)
                pair_corrected.append(sample.corrected_delta)
        pairs.append({"pair_id":pair.pair_id,"target_view_id":pair.target_view_id,"reference_view_id":pair.reference_view_id,
            "map_view_id":pair.map_view_id,"width":pair.width,"height":pair.height,"sample_count":len(pair.pixels),
            "expected_samples":sum(pair.expected_mask.values),"visible_samples":sum(pair.visible_mask.values),
            "comparable_samples":sum(pair.comparable_mask.values),"changed_samples":sum(pair.changed_mask.values),
            "unknown_samples":sum(pair.unknown_mask.values),"visibility_states":states,
            "raw_mean_delta":sum(pair_raw)/len(pair_raw) if pair_raw else None,
            "raw_max_delta":max(pair_raw) if pair_raw else None,
            "corrected_mean_delta":sum(pair_corrected)/len(pair_corrected) if pair_corrected else None,
            "corrected_max_delta":max(pair_corrected) if pair_corrected else None,
            "fitted_neutral_gain":pair.fitted_neutral_gain,"fitted_residual":pair.fitted_residual,
            "reference_eligibility":pair.reference_eligibility})
    return {"raw_mean_delta":sum(raw)/len(raw) if raw else None,"raw_max_delta":max(raw) if raw else None,
            "corrected_mean_delta":sum(corrected)/len(corrected) if corrected else None,
            "corrected_max_delta":max(corrected) if corrected else None},visibility,pairs


def mask_bounds(mask):
    occupied = [index for index,value in enumerate(mask.values) if value]
    if not occupied:
        return None
    xs,ys = [i%mask.width for i in occupied],[i//mask.width for i in occupied]
    return [min(xs)/max(1,mask.width-1),min(ys)/max(1,mask.height-1),
            max(xs)/max(1,mask.width-1),max(ys)/max(1,mask.height-1)]


def localization_metrics(variant, inputs, result):
    from core.diagnostics_preflight import RasterInput
    records = []
    for view in result.views:
        truth_asset = variant["views"][view.view_id]["truth_region_mask"]
        truth = RasterInput.from_path(inputs["corpus_root"]/truth_asset["path"])
        if (truth.width,truth.height)!=(view.width,view.height):
            raise ValueError("Fixture truth and measured localization grids differ; no silent resampling is allowed")
        expected = bytes(int(truth.rgba[i]>=.5) for i in range(3,len(truth.rgba),4))
        changed = view.changed_mask.values
        intersection = sum(bool(a and b) for a,b in zip(expected,changed))
        predicted = sum(changed)
        true_count = sum(expected)
        records.append({"view_id":view.view_id,"authored_region_pixels":true_count,"changed_pixels":predicted,
            "intersection_pixels":intersection,"extra_changed_pixels":predicted-intersection,
            "missed_region_pixels":true_count-intersection,
            "pixel_precision":intersection/predicted if predicted else None,
            "pixel_recall":intersection/true_count if true_count else None,
            "changed_bounds_normalized":mask_bounds(view.changed_mask),
            "authored_projected_bounds":variant["views"][view.view_id]["region_projected_bounds"],
            "truth_mask_sha256":truth_asset["sha256"]})
    return records
