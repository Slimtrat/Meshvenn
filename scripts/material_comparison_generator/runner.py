from __future__ import annotations

import time

import bpy

from scripts.run_logger import RunLogger

from .cli import parse_args, validate_args
from .config import load_pipeline_runtime
from .io import discover_sheets, write_json
from .sheet import process_sheet


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

    example_dir = (
        args.example_dir
        .resolve()
    )

    if args.output is None:
        output_root = (
            example_dir
            / "material-comparison"
        )

    else:
        output_root = (
            args.output
            .resolve()
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

    logger = RunLogger(
        jsonl_path=(
            output_root
            / "material-comparison.jsonl"
            if args.json_log
            else None
        )
    )

    logger.divider(
        "MESHVENN MATERIAL COMPARISON"
    )

    logger.info(
        "Blender",
        version=(
            bpy.app.version_string
        ),
    )

    logger.info(
        "Example",
        path=str(
            example_dir
        ),
    )

    logger.info(
        "Output",
        path=str(
            output_root
        ),
    )

    logger.info(
        "Profiles",
        value=", ".join(
            args.profiles
        ),
    )

    logger.info(
        "Implementations",
        value=", ".join(
            args.implementations
        ),
    )

    logger.info(
        "Geometry",
        resolution=(
            args.resolution
        ),
        mesh_mode=(
            args.mesh_mode
        ),
    )

    logger.info(
        "UV Bake preview",
        texture_size=(
            args.texture_size
        ),
        padding=(
            args.padding
        ),
        samples_per_axis=(
            args.samples_per_axis
        ),
    )

    started_at = (
        time.perf_counter()
    )

    global_manifest = {
        "example": str(
            example_dir
        ),

        "output": str(
            output_root
        ),

        "profiles": list(
            args.profiles
        ),

        "implementations": list(
            args.implementations
        ),

        "resolution": (
            args.resolution
        ),

        "mesh_mode": (
            args.mesh_mode
        ),

        "texture_size": (
            args.texture_size
        ),

        "sheets": {},
    }

    failures = []

    for (
        index,
        sheet_path,
    ) in enumerate(
        sheets,
        start=1,
    ):
        logger.progress(
            index,
            len(
                sheets
            ),
            sheet_path.name,
        )

        try:
            sheet_manifest = (
                process_sheet(
                    runtime,
                    sheet_path=(
                        sheet_path
                    ),
                    output_root=(
                        output_root
                    ),
                    args=args,
                    logger=(
                        logger.child()
                    ),
                )
            )

            global_manifest[
                "sheets"
            ][
                sheet_path.stem
            ] = (
                sheet_manifest
            )

        except Exception as exc:
            failures.append(
                {
                    "sheet": (
                        sheet_path.stem
                    ),
                    "error": str(
                        exc
                    ),
                    "exception_type": (
                        type(exc).__name__
                    ),
                }
            )

            logger.error(
                "sheet failed",
                sheet=(
                    sheet_path.stem
                ),
                error=str(
                    exc
                ),
            )

            if (
                not args
                .continue_on_error
            ):
                raise

    elapsed = (
        time.perf_counter()
        - started_at
    )

    global_manifest[
        "elapsed_seconds"
    ] = elapsed

    global_manifest[
        "failures"
    ] = failures

    global_manifest[
        "success"
    ] = (
        len(
            failures
        )
        == 0
    )

    manifest_path = (
        output_root
        / "comparison.json"
    )

    write_json(
        manifest_path,
        global_manifest,
    )

    logger.divider(
        "MATERIAL COMPARISON SUMMARY"
    )

    logger.info(
        "Sheets",
        count=len(
            sheets
        ),
    )

    logger.info(
        "Failures",
        count=len(
            failures
        ),
    )

    logger.info(
        "Elapsed",
        seconds=elapsed,
    )

    logger.success(
        "comparison generation finished",
        manifest=str(
            manifest_path
        ),
    )

    if failures:
        raise SystemExit(
            1
        )
