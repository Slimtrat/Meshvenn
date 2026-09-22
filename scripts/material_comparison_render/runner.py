from __future__ import annotations

import time
from pathlib import Path

from .cli import parse_args, validate_args
from .sheet import process_sheet
from .variants import discover_sheets, write_json

# =========================================================
# Markdown index
# =========================================================

def write_markdown_index(
    comparison_root: Path,
    *,
    sheets: list[str],
    profiles: list[str],
    implementations: list[str],
) -> Path:
    path = (
        comparison_root
        / "MATERIAL_COMPARISON.md"
    )

    lines = [
        "# Meshvenn Material Comparison",
        "",
        "Generated visual comparison of MATERIAL implementations.",
        "",
        "## Matrix layout",
        "",
        "Columns:",
        "",
    ]

    for (
        index,
        implementation,
    ) in enumerate(
        implementations,
        start=1,
    ):
        lines.append(
            (
                f"{index}. "
                f"`{implementation}`"
            )
        )

    lines.extend(
        [
            "",
            "Rows:",
            "",
        ]
    )

    for (
        index,
        profile,
    ) in enumerate(
        profiles,
        start=1,
    ):
        lines.append(
            (
                f"{index}. "
                f"`{profile}`"
            )
        )

    lines.extend(
        [
            "",
            "Every cell uses the same turntable angles, "
            "camera logic, lighting and Cycles settings.",
            "",
        ]
    )

    for sheet in sheets:
        relative = (
            Path(sheet)
            / "material_comparison.png"
        )

        lines.extend(
            [
                f"## {sheet}",
                "",
                (
                    f"![{sheet} MATERIAL comparison]"
                    f"({relative.as_posix()})"
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


# =========================================================
# Main
# =========================================================

def main() -> None:
    args = (
        parse_args()
    )

    validate_args(
        args
    )

    comparison_root = (
        args
        .comparison_root
        .resolve()
    )

    sheets = (
        discover_sheets(
            comparison_root,
            args.sheets,
        )
    )

    print(
        "=" * 72
    )

    print(
        "MESHVENN MATERIAL VISUAL COMPARISON"
    )

    print(
        "=" * 72
    )

    print(
        (
            "Comparison root: "
            f"{comparison_root}"
        )
    )

    print(
        (
            "Sheets: "
            + ", ".join(
                sheets
            )
        )
    )

    print(
        (
            "Profiles: "
            + ", ".join(
                args.profiles
            )
        )
    )

    print(
        (
            "Implementations: "
            + ", ".join(
                args.implementations
            )
        )
    )

    print(
        (
            "Views: "
            f"{args.views}"
        )
    )

    print(
        (
            "Tile size: "
            f"{args.size}px"
        )
    )

    print(
        (
            "Cycles samples: "
            f"{args.samples}"
        )
    )

    started_at = (
        time.perf_counter()
    )

    results = {}

    failures = []

    for (
        index,
        sheet,
    ) in enumerate(
        sheets,
        start=1,
    ):
        print()

        print(
            (
                f"[{index}/{len(sheets)}] "
                f"{sheet}"
            )
        )

        try:
            result = (
                process_sheet(
                    comparison_root,

                    sheet=sheet,

                    profiles=(
                        args.profiles
                    ),

                    implementations=(
                        args
                        .implementations
                    ),

                    args=args,
                )
            )

            results[
                sheet
            ] = (
                result
            )

            if not result[
                "success"
            ]:
                failures.append(
                    sheet
                )

        except Exception as exc:
            results[
                sheet
            ] = {
                "success": False,

                "error": str(
                    exc
                ),

                "type": (
                    type(
                        exc
                    ).__name__
                ),
            }

            failures.append(
                sheet
            )

            if (
                not args
                .continue_on_error
            ):
                raise

    markdown_path = (
        write_markdown_index(
            comparison_root,

            sheets=sheets,

            profiles=(
                args.profiles
            ),

            implementations=(
                args
                .implementations
            ),
        )
    )

    elapsed = (
        time.perf_counter()
        - started_at
    )

    global_manifest = {
        "success": (
            len(
                failures
            )
            == 0
        ),

        "comparison_root": str(
            comparison_root
        ),

        "sheets": (
            results
        ),

        "sheet_order": (
            sheets
        ),

        "profile_order": (
            args.profiles
        ),

        "implementation_order": (
            args
            .implementations
        ),

        "views": (
            args.views
        ),

        "render_size": (
            args.size
        ),

        "cycles_samples": (
            args.samples
        ),

        "gutter": (
            args.gutter
        ),

        "markdown": str(
            markdown_path
        ),

        "failures": (
            failures
        ),

        "elapsed_seconds": (
            elapsed
        ),
    }

    manifest_path = (
        comparison_root
        / "render_comparison.json"
    )

    write_json(
        manifest_path,
        global_manifest,
    )

    print()

    print(
        "=" * 72
    )

    print(
        "MATERIAL COMPARISON SUMMARY"
    )

    print(
        "=" * 72
    )

    print(
        (
            "Sheets: "
            f"{len(sheets)}"
        )
    )

    print(
        (
            "Failures: "
            f"{len(failures)}"
        )
    )

    print(
        (
            "Elapsed: "
            f"{elapsed:.2f}s"
        )
    )

    print(
        (
            "Index: "
            f"{markdown_path}"
        )
    )

    print(
        (
            "Manifest: "
            f"{manifest_path}"
        )
    )

    if failures:
        raise SystemExit(
            1
        )
