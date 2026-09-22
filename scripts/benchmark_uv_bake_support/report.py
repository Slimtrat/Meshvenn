from __future__ import annotations

from .shared import Any, BenchmarkVariant, PROJECTED_IMPLEMENTATION_ID, Path, math

def benchmark_row(
    variant: BenchmarkVariant,
) -> dict[str, Any]:
    info = (
        variant.info
    )

    result_metrics = (
        info
        .get(
            "result",
            {}
        )
        .get(
            "metrics",
            {}
        )
    )

    bake = (
        info.get(
            "uv_bake"
        )
    )

    if not isinstance(
        bake,
        dict,
    ):
        bake = {}

    return {
        "sheet": (
            variant.sheet
        ),

        "profile": (
            variant.profile
        ),

        "implementation": (
            variant
            .implementation
        ),

        "texture_size": (
            variant.texture_size
        ),

        "vertices": (
            info[
                "geometry"
            ][
                "vertices"
            ]
        ),

        "faces": (
            info[
                "geometry"
            ][
                "faces"
            ]
        ),

        "material_seconds": (
            info[
                "material_seconds"
            ]
        ),

        "render_seconds": (
            variant
            .render_seconds
        ),

        "glb_bytes": (
            info[
                "glb_bytes"
            ]
        ),

        "texture_png_bytes": (
            info.get(
                "texture_png_bytes"
            )
        ),

        "coverage_ratio": (
            bake.get(
                "coverage_ratio"
            )
        ),

        "filled_ratio": (
            bake.get(
                "filled_ratio"
            )
        ),

        "covered_pixels": (
            bake.get(
                "covered_pixels"
            )
        ),

        "filled_pixels": (
            bake.get(
                "filled_pixels"
            )
        ),

        "surface_samples": (
            bake.get(
                "surface_samples"
            )
        ),

        "fallback_samples": (
            bake.get(
                "fallback_samples"
            )
        ),

        "subpixel_triangle_ratio": (
            result_metrics.get(
                "uv_subpixel_triangle_ratio"
            )
        ),

        "mean_triangle_area_pixels": (
            result_metrics.get(
                "uv_mean_triangle_area_pixels"
            )
        ),

        "effective_island_margin_pixels": (
            info
            .get(
                "result",
                {}
            )
            .get(
                "metadata",
                {}
            )
            .get(
                "effective_island_margin_pixels"
            )
        ),

        "rgb_mae_vs_projected": (
            variant
            .rgb_mae_vs_baseline
        ),

        "rgb_rmse_vs_projected": (
            variant
            .rgb_rmse_vs_baseline
        ),

        "psnr_vs_projected": (
            variant
            .psnr_vs_baseline
        ),

        "changed_pixel_ratio_vs_projected": (
            variant
            .changed_pixel_ratio_vs_baseline
        ),

        "model": str(
            variant
            .model_path
        ),

        "render": str(
            variant
            .contact_sheet_path
        ),

        "texture": (
            info.get(
                "texture_png"
            )
        ),
    }

def _percent(
    value,
) -> str:
    if value is None:
        return "-"

    return (
        f"{float(value) * 100.0:.2f}%"
    )

def _seconds(
    value,
) -> str:
    if value is None:
        return "-"

    return (
        f"{float(value):.2f}s"
    )

def _mib(
    value,
) -> str:
    if value is None:
        return "-"

    return (
        f"{float(value) / (1024.0 * 1024.0):.2f}"
    )

def _float_value(
    value,
    digits: int = 4,
) -> str:
    if value is None:
        return "-"

    if (
        isinstance(
            value,
            float,
        )
        and math.isinf(
            value
        )
    ):
        return "∞"

    return (
        f"{float(value):.{digits}f}"
    )

def write_markdown(
    output_root: Path,
    *,
    rows: list[
        dict[str, Any]
    ],
    profiles: list[str],
    texture_sizes: list[int],
    recommendation: dict[str, Any],
) -> Path:
    path = (
        output_root
        / "BENCHMARK.md"
    )

    columns = [
        "Projected V1.2",
        *[
            f"UV {size}²"
            for size
            in texture_sizes
        ],
    ]

    lines = [
        "# Meshvenn — UV Bake Resolution Benchmark",
        "",
        "## Visual matrix",
        "",
        "Columns, left to right:",
        "",
        *[
            (
                f"{index}. `{column}`"
            )
            for (
                index,
                column,
            )
            in enumerate(
                columns,
                start=1,
            )
        ],
        "",
        "Rows, top to bottom:",
        "",
        *[
            (
                f"{index}. `{profile}`"
            )
            for (
                index,
                profile,
            )
            in enumerate(
                profiles,
                start=1,
            )
        ],
        "",
        "![UV Bake resolution benchmark](benchmark_matrix.png)",
        "",
        "## Metrics",
        "",
        (
            "| Profile | Variant | Bake | Coverage | "
            "Filled | Subpixel tris | Mean tri px² | "
            "GLB MiB | Texture MiB | RGB MAE vs projected | "
            "PSNR vs projected |"
        ),
        (
            "| --- | --- | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: | ---: |"
        ),
    ]

    for row in rows:
        if (
            row[
                "implementation"
            ]
            == PROJECTED_IMPLEMENTATION_ID
        ):
            label = (
                "Projected V1.2"
            )

        else:
            label = (
                "UV "
                f"{row['texture_size']}²"
            )

        lines.append(
            (
                f"| {row['profile']} "
                f"| {label} "
                f"| {_seconds(row['material_seconds'])} "
                f"| {_percent(row['coverage_ratio'])} "
                f"| {_percent(row['filled_ratio'])} "
                f"| {_percent(row['subpixel_triangle_ratio'])} "
                f"| {_float_value(row['mean_triangle_area_pixels'], 2)} "
                f"| {_mib(row['glb_bytes'])} "
                f"| {_mib(row['texture_png_bytes'])} "
                f"| {_float_value(row['rgb_mae_vs_projected'], 5)} "
                f"| {_float_value(row['psnr_vs_projected'], 2)} |"
            )
        )

    lines.extend(
        [
            "",
            "## Technical candidate",
            "",
            (
                "**Texture size:** "
                f"`{recommendation['texture_size']}²`"
            ),
            "",
            (
                "**Subpixel target:** "
                f"`{recommendation['max_subpixel_ratio'] * 100.0:.1f}%`"
            ),
            "",
            (
                "**Target met:** "
                f"`{recommendation['target_met']}`"
            ),
            "",
            recommendation[
                "reason"
            ],
            "",
            (
                "> This recommendation only evaluates UV "
                "sampling density and successful bake coverage. "
                "The final product default should also be chosen "
                "from the visual matrix."
            ),
            "",
        ]
    )

    path.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    return path
