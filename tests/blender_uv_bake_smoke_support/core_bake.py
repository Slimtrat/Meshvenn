from __future__ import annotations

import importlib
import math
from pathlib import Path
from typing import Any

import bpy

from .constants import *
from .support import (_clamp01, _purge_package_modules, _quantize_unorm8, _require, _require_close, _require_rgba8_close, _section)

# =========================================================
# Core UV bake
# =========================================================

def _run_core_bake(
    uv_bake_module,
    triangles,
):
    _section(
        "core bake"
    )

    # -----------------------------------------------------
    # Synthetic shader:
    #
    #     R = X
    #     G = Y
    #     B = 0.25
    #     A = 1.0
    #
    # Since X/Y == U/V, texels are deterministic.
    # -----------------------------------------------------

    def sampler(
        position,
        normal,
    ):
        _require_close(
            normal[0],
            0.0,
            message=(
                "Sampler received invalid "
                "normal X."
            ),
        )

        _require_close(
            normal[1],
            0.0,
            message=(
                "Sampler received invalid "
                "normal Y."
            ),
        )

        _require_close(
            normal[2],
            1.0,
            message=(
                "Sampler received invalid "
                "normal Z."
            ),
        )

        return (
            uv_bake_module
            .SurfaceColorSample(
                color=(
                    position[0],
                    position[1],
                    0.25,
                    1.0,
                ),
                used_fallback=False,
                selected_samples=2,
            )
        )

    result = (
        uv_bake_module
        .bake_uv_texture(
            triangles,
            sampler,
            config=(
                uv_bake_module
                .UVBakeConfig(
                    width=TEXTURE_SIZE,
                    height=TEXTURE_SIZE,
                    padding_pixels=0,
                    samples_per_axis=1,
                )
            ),
        )
    )

    stats = (
        result.stats
    )

    _require(
        stats.triangle_count
        == 2,
        (
            "Unexpected triangle count."
        ),
    )

    _require(
        stats.rasterized_triangles
        == 2,
        (
            "Both test triangles "
            "must rasterize."
        ),
    )

    _require(
        stats.degenerate_triangles
        == 0,
        (
            "Test mesh must contain no "
            "degenerate UV triangle."
        ),
    )

    expected_pixels = (
        TEXTURE_SIZE
        * TEXTURE_SIZE
    )

    _require(
        stats.covered_pixels
        == expected_pixels,
        (
            "Unit square UV map should "
            "cover the entire texture.\n"
            f"Expected: {expected_pixels}\n"
            f"Actual:   "
            f"{stats.covered_pixels}"
        ),
    )

    _require(
        stats.padded_pixels
        == 0,
        (
            "Padding must be disabled "
            "for this smoke."
        ),
    )

    _require(
        stats.surface_samples
        >= stats.covered_pixels,
        (
            "Surface sample count cannot "
            "be smaller than coverage."
        ),
    )

    _require(
        stats.selected_source_samples
        == (
            stats.surface_samples
            * 2
        ),
        (
            "SurfaceColorSample selected "
            "sample diagnostics are wrong."
        ),
    )

    _require(
        stats.fallback_samples
        == 0,
        (
            "Synthetic sampler must not "
            "report fallback samples."
        ),
    )

    _require_close(
        stats.coverage_ratio,
        1.0,
        message=(
            "Expected complete UV coverage."
        ),
    )

    print(
        "Core UV bake: OK"
    )

    print(
        (
            "  resolution: "
            f"{result.texture.width}×"
            f"{result.texture.height}"
        )
    )

    print(
        (
            "  covered:    "
            f"{stats.covered_pixels}"
        )
    )

    print(
        (
            "  overlaps:   "
            f"{stats.overlap_pixels}"
        )
    )

    print(
        (
            "  samples:    "
            f"{stats.surface_samples}"
        )
    )

    return result
