"""Color evidence, independent of atlas occupancy and geometry fidelity."""

from __future__ import annotations

import math


def image_signal(pixels, occupied):
    count = chromatic = white = 0
    red = green = blue = 0.0
    for index, enabled in enumerate(occupied):
        if not enabled:
            continue
        rgb = tuple(float(pixels[index * 4 + axis]) for axis in range(3))
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in rgb):
            raise ValueError("Appearance contains nonfinite or out-of-range pixels.")
        count += 1
        chromatic += max(rgb) - min(rgb) > .10
        white += min(rgb) > .94
        red += rgb[0]
        green += rgb[1]
        blue += rgb[2]
    if not count:
        raise ValueError("Appearance has no occupied pixels.")
    return {"occupied_pixels": count, "chromatic_fraction": chromatic / count,
            "white_fraction": white / count, "mean_linear_rgb": [red/count, green/count, blue/count]}


def certify_appearance(bake_result, diagnostics, source_signals):
    stats = bake_result.stats
    signal = image_signal(bake_result.texture.pixels, bake_result.coverage)
    required = ("total_samples", "candidate_samples", "source_rejected_samples", "visible_samples",
                "occluded_samples", "front_facing_samples", "backface_samples", "grazing_rejected_samples",
                "primary_samples", "projected_fallback_samples", "neutral_fallback_samples", "selected_samples")
    if any(name not in diagnostics or type(diagnostics[name]) is not int or diagnostics[name] < 0 for name in required):
        raise ValueError("Appearance sampling diagnostics must contain all nonnegative integer counters.")
    if type(stats.surface_samples) is not int or stats.surface_samples <= 0:
        raise ValueError("Appearance surface_samples must be positive.")
    primary, projected, neutral = (diagnostics[name] for name in
                                   ("primary_samples", "projected_fallback_samples", "neutral_fallback_samples"))
    if (primary + projected + neutral != stats.surface_samples or
            projected + neutral != stats.fallback_samples or
            diagnostics["selected_samples"] != stats.selected_source_samples or
            diagnostics["total_samples"] != stats.surface_samples * len(source_signals) or
            diagnostics["candidate_samples"] + diagnostics["source_rejected_samples"] != diagnostics["total_samples"] or
            diagnostics["visible_samples"] + diagnostics["occluded_samples"] != diagnostics["candidate_samples"] or
            diagnostics["front_facing_samples"] + diagnostics["backface_samples"] != diagnostics["visible_samples"]):
        raise ValueError("Appearance sampling counters contradict actual bake work.")
    for item in source_signals:
        if (type(item["occupied_pixels"]) is not int or item["occupied_pixels"] <= 0 or
                any(not math.isfinite(item[key]) or not 0 <= item[key] <= 1 for key in
                    ("chromatic_fraction", "white_fraction"))):
            raise ValueError("Appearance source signal must be finite, occupied and bounded.")
        mean = item.get("mean_linear_rgb")
        if mean is not None and (len(mean) != 3 or any(not math.isfinite(value) or not 0 <= value <= 1 for value in mean)):
            raise ValueError("Appearance source mean RGB must be finite in [0, 1].")
    result = {"texture_size": stats.texture_width, "samples_per_axis": stats.samples_per_axis,
              "surface_samples": stats.surface_samples,
              "fallback_ratio": stats.fallback_samples / stats.surface_samples,
              "neutral_fallback_ratio": neutral / stats.surface_samples,
              "sampling_diagnostics": diagnostics, "atlas_signal": signal,
              "source_view_signals": source_signals,
              "scope": "source-color transport only; not general texture reconstruction quality"}
    # Real color and successful source sampling, never mere atlas occupancy.
    passed = (len(source_signals) == 10 and len({item["name"] for item in source_signals}) == 10
              and all(item["chromatic_fraction"] > .90 for item in source_signals)
              and signal["chromatic_fraction"] > .90 and signal["white_fraction"] < .01
              and result["neutral_fallback_ratio"] < .01)
    result["passed"] = passed
    if not passed:
        raise AssertionError(f"Source-color appearance gate failed: {result}")
    return result
