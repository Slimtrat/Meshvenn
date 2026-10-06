"""Preview only the measured color transport, independently of geometry scores."""
from __future__ import annotations

import math
import re


def _fraction(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid appearance fraction.")
    return value


def verify_appearance(manifest):
    if (manifest.get("geometry_input_mode") != "neutral-silhouette"
            or manifest.get("material_input_mode") != "source-color-projection"):
        raise ValueError("Modern preview requires separate neutral geometry and real source-color appearance inputs.")
    value = manifest["appearance"]
    if (value.get("passed") is not True or value.get("render_mode") != "base-color-emission"
            or value.get("projection_convention") != "native-normalized"
            or value.get("source_sha256") != manifest["source_sha256"]
            or value.get("texture_size") != 512 or value.get("samples_per_axis") != 2
            or type(value.get("surface_samples")) is not int or value["surface_samples"] <= 0):
        raise ValueError("The source-color appearance evidence is incomplete.")
    if not re.fullmatch(r"[0-9a-f]{64}", value["source_sha256"]):
        raise ValueError("Invalid source-color input hash.")
    fallback, neutral = _fraction(value["fallback_ratio"]), _fraction(value["neutral_fallback_ratio"])
    signal = value["atlas_signal"]
    signals = value["source_view_signals"]
    views = value["views"]
    expected = {"000", "045", "090", "135", "180", "225", "270", "315", "TOP", "BOT"}
    if (neutral >= .01 or neutral > fallback or _fraction(signal["chromatic_fraction"]) <= .90
            or _fraction(signal["white_fraction"]) >= .01 or len(signals) != 10 or len(views) != 10
            or {item["name"] for item in signals} != expected or {item["name"] for item in views} != expected
            or any(_fraction(item["chromatic_fraction"]) <= .90 for item in signals)):
        raise ValueError("The actual source-color signal/fallback gates did not pass.")
    for item in views:
        if (not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                or type(item.get("width")) is not int or not 1 <= item["width"] <= 2048
                or type(item.get("height")) is not int or not 1 <= item["height"] <= 2048
                or type(item.get("alpha_occupied_pixels")) is not int
                or not 0 < item["alpha_occupied_pixels"] <= item["width"] * item["height"]):
            raise ValueError("Source-color projection provenance is invalid.")
    diagnostics = value["sampling_diagnostics"]
    keys = ("total_samples", "candidate_samples", "source_rejected_samples", "visible_samples", "occluded_samples",
            "front_facing_samples", "backface_samples", "grazing_rejected_samples", "primary_samples",
            "projected_fallback_samples", "neutral_fallback_samples", "selected_samples")
    if any(type(diagnostics.get(key)) is not int or diagnostics[key] < 0 for key in keys):
        raise ValueError("Appearance sampling diagnostics are missing or invalid.")
    samples = value["surface_samples"]
    if (diagnostics["primary_samples"] + diagnostics["projected_fallback_samples"] + diagnostics["neutral_fallback_samples"] != samples
            or diagnostics["total_samples"] != samples * 10
            or diagnostics["candidate_samples"] + diagnostics["source_rejected_samples"] != diagnostics["total_samples"]
            or diagnostics["visible_samples"] + diagnostics["occluded_samples"] != diagnostics["candidate_samples"]
            or diagnostics["front_facing_samples"] + diagnostics["backface_samples"] != diagnostics["visible_samples"]
            or diagnostics["visible_samples"] <= 0 or diagnostics["occluded_samples"] <= 0
            or not diagnostics["primary_samples"] <= diagnostics["selected_samples"] <= diagnostics["visible_samples"]
            or not math.isclose(neutral, diagnostics["neutral_fallback_samples"] / samples, abs_tol=1e-12)
            or not math.isclose(fallback, (diagnostics["projected_fallback_samples"] + diagnostics["neutral_fallback_samples"]) / samples, abs_tol=1e-12)):
        raise ValueError("Appearance diagnostic counts do not support the reported sampling ratios.")
    if (manifest["material"].get("surface_samples") != samples
            or manifest["material"].get("selected_source_samples") != diagnostics["selected_samples"]
            or manifest["material"].get("fallback_samples") != diagnostics["projected_fallback_samples"] + diagnostics["neutral_fallback_samples"]):
        raise ValueError("Appearance diagnostics contradict the UV Bake result.")
    transport = value["color_transport"]
    tolerance = _fraction(transport["tolerance"])
    source = transport["source_linear_rgb"]
    if (value.get("atlas_storage") != "srgb-byte-from-scene-linear" or transport.get("passed") is not True
            or not 0 < tolerance <= .004 or not isinstance(source, list) or source != [.25, .5, .75]):
        raise ValueError("The source-color atlas lacks the measured linear/sRGB transport proof.")
    maximum = 0.0
    for key in ("source_projection_linear_rgb", "baked_shader_linear_rgb", "reimported_shader_linear_rgb"):
        rgb = transport[key]
        if not isinstance(rgb, list) or len(rgb) != 3:
            raise ValueError("Invalid measured color-transport triplet.")
        maximum = max(maximum, *(abs(_fraction(value) - expected) for value, expected in zip(rgb, source)))
    if not maximum <= tolerance or not math.isclose(_fraction(transport["max_linear_error"]), maximum, abs_tol=2e-7):
        raise ValueError("The measured linear/sRGB transport error is inconsistent or exceeds tolerance.")


def appearance_caption(value):
    return ("La géométrie conserve dix silhouettes neutralisées. L’apparence est une voie séparée : "
            "dix vues couleur de la source (base-color emission), UV Bake V2 512², 2×2 échantillons. "
            f"Signal chromatique de l’atlas : **{value['atlas_signal']['chromatic_fraction']:.4%}** ; "
            f"fallback total : **{value['fallback_ratio']:.3%}** ; fallback neutre "
            f"**{value['neutral_fallback_ratio']:.4%}** "
            f"({value['sampling_diagnostics']['neutral_fallback_samples']}/{value['surface_samples']} échantillons). "
            f"Probe RGB linéaire export/réimport : erreur max **{value['color_transport']['max_linear_error']:.5f}** "
            f"(limite {value['color_transport']['tolerance']:.3f}). "
            "Ces gates certifient le transport de couleur sur cette fixture, pas la qualité générale de reconstruction des textures.")
