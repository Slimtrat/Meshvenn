from __future__ import annotations

import argparse
from pathlib import Path

from core.projected_material import BLEND_MODE, MATERIAL_MODE, VISIBILITY_MODE
from scripts.generate_example_native import process_sheet
from scripts.run_logger import RunLogger

from .discovery import discover_examples, discover_sheets, filter_from_sheet
from .options import REPO_ROOT, normalize_profiles, parse_args, validate_numeric_args

# ---------------------------------------------------------
# Execution plan
# ---------------------------------------------------------

def print_plan(
    logger: RunLogger,
    sheets: list[
        tuple[
            Path,
            Path,
        ]
    ],
    *,
    examples_root: Path,
    args: argparse.Namespace,
) -> None:
    logger.divider(
        "NATIVE C++ GENERATION PLAN"
    )

    logger.info(
        "Engine",
        value="native-cpp",
    )

    logger.info(
        "Resolution",
        value=(
            args.resolution
        ),
    )

    logger.info(
        "Profiles",
        value=(
            ", ".join(
                args.profiles
            )
            if args.profiles
            else "all runnable"
        ),
    )

    logger.info(
        "Mesh mode",
        value=(
            args.mesh_mode
        ),
    )

    logger.info(
        "Material mode",
        value=(
            MATERIAL_MODE
        ),
    )

    logger.info(
        "Material visibility",
        value=(
            VISIBILITY_MODE
        ),
    )

    logger.info(
        "Material blend",
        value=(
            BLEND_MODE
        ),
    )

    logger.info(
        "Voxel size",
        value=(
            args.voxel_size
        ),
    )

    logger.info(
        "Target height",
        value=(
            args.target_height
        ),
    )

    logger.info(
        "Threads",
        value=(
            args.thread_count
            if args.thread_count > 0
            else "auto"
        ),
    )

    logger.info(
        "Symmetry X",
        value=(
            args.symmetry_x
        ),
    )

    logger.info(
        "Sheets",
        count=len(
            sheets
        ),
    )

    for index, (
        _example_dir,
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
            (
                sheet_path
                .relative_to(
                    examples_root
                )
                .as_posix()
            ),
        )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main() -> None:
    args = parse_args()

    validate_numeric_args(
        args
    )

    args.profiles = (
        normalize_profiles(
            args.profiles
        )
    )

    examples_root = (
        args.examples.resolve()
    )

    example_dirs = (
        discover_examples(
            examples_root,
            args.example,
        )
    )

    sheets = (
        discover_sheets(
            example_dirs
        )
    )

    if not sheets:
        raise RuntimeError(
            "No sheet*.png found."
        )

    sheets = filter_from_sheet(
        sheets,
        examples_root=(
            examples_root
        ),
        start_sheet=(
            args.start_sheet
        ),
    )

    if not sheets:
        raise RuntimeError(
            (
                "No sheets remain "
                "after filtering."
            )
        )

    logger = RunLogger(
        jsonl_path=(
            REPO_ROOT
            / "native_batch.jsonl"
            if args.json_log
            else None
        )
    )

    print_plan(
        logger,
        sheets,
        examples_root=(
            examples_root
        ),
        args=args,
    )

    failures: list[
        tuple[
            Path,
            Exception,
        ]
    ] = []

    total = len(
        sheets
    )

    for index, (
        example_dir,
        sheet_path,
    ) in enumerate(
        sheets,
        start=1,
    ):
        relative_sheet = (
            sheet_path
            .relative_to(
                examples_root
            )
            .as_posix()
        )

        logger.progress(
            index,
            total,
            relative_sheet,
        )

        generated_root = (
            example_dir
            / "generated"
        )

        try:
            process_sheet(
                sheet_path,
                generated_root,
                args,
                logger=(
                    logger.child()
                ),
            )

        except Exception as exc:
            failures.append(
                (
                    sheet_path,
                    exc,
                )
            )

            logger.error(
                (
                    f"FAILED "
                    f"{relative_sheet}"
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

    succeeded = (
        total
        - len(
            failures
        )
    )

    logger.divider(
        "NATIVE GENERATION SUMMARY"
    )

    logger.info(
        "Processed",
        count=total,
    )

    logger.info(
        "Succeeded",
        count=succeeded,
    )

    logger.info(
        "Failed",
        count=len(
            failures
        ),
    )

    logger.info(
        "Mesh mode",
        value=(
            args.mesh_mode
        ),
    )

    logger.info(
        "Material mode",
        value=(
            MATERIAL_MODE
        ),
    )

    logger.info(
        "Material visibility",
        value=(
            VISIBILITY_MODE
        ),
    )

    logger.info(
        "Material blend",
        value=(
            BLEND_MODE
        ),
    )

    for (
        sheet_path,
        error,
    ) in failures:
        logger.error(
            (
                sheet_path
                .relative_to(
                    examples_root
                )
                .as_posix()
            ),
            error=str(
                error
            ),
        )

    if failures:
        raise SystemExit(
            1
        )

    logger.success(
        "Native batch completed",
        elapsed=(
            logger.total_elapsed()
        ),
    )
