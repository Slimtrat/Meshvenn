from __future__ import annotations

from .shared import Any, PROJECTED_IMPLEMENTATION_ID, RunLogger, load_pipeline_runtime, shutil, time
from .artifacts import write_json
from .cli import parse_args, validate_args
from .discovery import discover_sheets
from .matrix import compose_matrix
from .recommendation import recommend_resolution
from .report import _float_value, _mib, _percent, benchmark_row, write_markdown
from .runner import benchmark_sheet

def print_results(
    rows: list[
        dict[str, Any]
    ],
) -> None:
    print()

    print(
        "=" * 118
    )

    print(
        "UV BAKE RESOLUTION BENCHMARK"
    )

    print(
        "=" * 118
    )

    print(
        (
            "PROFILE | VARIANT              | BAKE    | "
            "COVERAGE | SUBPIXEL | GLB MiB | "
            "RGB MAE | PSNR"
        )
    )

    print(
        "-" * 118
    )

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
                f"UV {row['texture_size']}²"
            )

        print(
            (
                f"{row['profile']:>7} | "
                f"{label:<20} | "
                f"{float(row['material_seconds']):>6.2f}s | "
                f"{_percent(row['coverage_ratio']):>8} | "
                f"{_percent(row['subpixel_triangle_ratio']):>8} | "
                f"{_mib(row['glb_bytes']):>7} | "
                f"{_float_value(row['rgb_mae_vs_projected'], 5):>7} | "
                f"{_float_value(row['psnr_vs_projected'], 2):>6}"
            )
        )

    print(
        "=" * 118
    )

def main() -> None:
    args = (
        parse_args()
    )

    validate_args(
        args
    )

    example_dir = (
        args
        .example_dir
        .resolve()
    )

    output_root = (
        args
        .output
        .resolve()
    )

    # Benchmark output is disposable and must never contain
    # stale data from a previous resolution run.
    if output_root.exists():
        shutil.rmtree(
            output_root
        )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    sheets = (
        discover_sheets(
            example_dir,
            args.sheets,
        )
    )

    runtime = (
        load_pipeline_runtime()
    )

    logger = (
        RunLogger()
    )

    started_at = (
        time.perf_counter()
    )

    all_rows: list[
        dict[str, Any]
    ] = []

    failures = []

    global_matrix_cells = {}

    for sheet_path in sheets:
        try:
            (
                variants,
                sheet_cells,
            ) = (
                benchmark_sheet(
                    runtime,

                    sheet_path=(
                        sheet_path
                    ),

                    output_root=(
                        output_root
                    ),

                    args=(
                        args
                    ),

                    logger=(
                        logger
                    ),
                )
            )

            rows = [
                benchmark_row(
                    variant
                )
                for variant
                in variants
            ]

            all_rows.extend(
                rows
            )

            # -------------------------------------------------
            # For the initial benchmark we expect one sheet.
            #
            # If several sheets are requested, each sheet gets
            # its own visual matrix.
            # -------------------------------------------------

            columns = [
                "projected",
                *[
                    f"uv-{size}"
                    for size
                    in args
                    .texture_sizes
                ],
            ]

            sheet_matrix = (
                output_root
                / sheet_path.stem
                / "benchmark_matrix.png"
            )

            compose_matrix(
                sheet_cells,

                profiles=(
                    args.profiles
                ),

                columns=(
                    columns
                ),

                output_path=(
                    sheet_matrix
                ),

                gutter=(
                    args.gutter
                ),
            )

            if len(
                sheets
            ) == 1:
                shutil.copyfile(
                    sheet_matrix,

                    output_root
                    / "benchmark_matrix.png",
                )

            global_matrix_cells[
                sheet_path.stem
            ] = str(
                sheet_matrix
            )

        except Exception as exc:
            failures.append(
                {
                    "sheet": (
                        sheet_path.stem
                    ),

                    "type": (
                        type(
                            exc
                        ).__name__
                    ),

                    "error": str(
                        exc
                    ),
                }
            )

            if not (
                args
                .continue_on_error
            ):
                raise

    if not all_rows:
        raise RuntimeError(
            (
                "Benchmark produced "
                "no result rows."
            )
        )

    recommendation = (
        recommend_resolution(
            all_rows,

            profiles=(
                args.profiles
            ),

            texture_sizes=(
                args.texture_sizes
            ),

            max_subpixel_ratio=(
                args
                .max_subpixel_ratio
            ),
        )
    )

    elapsed = (
        time.perf_counter()
        - started_at
    )

    manifest = {
        "success": (
            len(
                failures
            )
            == 0
        ),

        "example_dir": str(
            example_dir
        ),

        "output": str(
            output_root
        ),

        "geometry": {
            "resolution": (
                args.resolution
            ),

            "mesh_mode": (
                args.mesh_mode
            ),

            "voxel_size": (
                args.voxel_size
            ),

            "target_height": (
                args.target_height
            ),
        },

        "benchmark": {
            "profiles": (
                args.profiles
            ),

            "texture_sizes": (
                args.texture_sizes
            ),

            "padding_pixels": (
                args.padding
            ),

            "samples_per_axis": (
                args
                .samples_per_axis
            ),

            "render_size": (
                args.render_size
            ),

            "views": (
                args.views
            ),

            "render_samples": (
                args.render_samples
            ),

            "max_subpixel_ratio": (
                args
                .max_subpixel_ratio
            ),
        },

        "rows": (
            all_rows
        ),

        "recommendation": (
            recommendation
        ),

        "matrices": (
            global_matrix_cells
        ),

        "failures": (
            failures
        ),

        "elapsed_seconds": (
            elapsed
        ),
    }

    write_json(
        (
            output_root
            / "benchmark.json"
        ),
        manifest,
    )

    markdown_path = (
        write_markdown(
            output_root,

            rows=(
                all_rows
            ),

            profiles=(
                args.profiles
            ),

            texture_sizes=(
                args.texture_sizes
            ),

            recommendation=(
                recommendation
            ),
        )
    )

    print_results(
        all_rows
    )

    print()

    print(
        (
            "Technical candidate: "
            f"{recommendation['texture_size']}²"
        )
    )

    print(
        (
            "Target met: "
            f"{recommendation['target_met']}"
        )
    )

    print(
        (
            "Benchmark JSON: "
            f"{output_root / 'benchmark.json'}"
        )
    )

    print(
        (
            "Benchmark Markdown: "
            f"{markdown_path}"
        )
    )

    print(
        (
            "Elapsed: "
            f"{elapsed:.2f}s"
        )
    )

    if failures:
        raise SystemExit(
            1
        )
