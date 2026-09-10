from __future__ import annotations

import argparse
import sys

from pathlib import Path


REPO_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPO_ROOT),
    )


from core.projected_material import (
    BLEND_MODE,
    MATERIAL_MODE,
    VISIBILITY_MODE,
)
from scripts.generate_example_native import (
    process_sheet,
)
from scripts.run_logger import (
    RunLogger,
)


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def parse_args() -> argparse.Namespace:
    argv = sys.argv

    if "--" in argv:
        argv = argv[
            argv.index("--") + 1:
        ]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Generate Projection Tool examples "
            "with the native C++ engine inside "
            "one Blender process."
        )
    )

    parser.add_argument(
        "--examples",
        type=Path,
        default=(
            REPO_ROOT
            / "example"
        ),
    )

    parser.add_argument(
        "--example",
        default="all",
        help=(
            '"all" or an example path '
            'such as "mascotte/test1".'
        ),
    )

    parser.add_argument(
        "--start-sheet",
        default="",
        help=(
            "Optional sheet name/path "
            "to resume generation from."
        ),
    )

    parser.add_argument(
        "--profiles",
        nargs="*",
        default=None,
        help=(
            "Optional scan levels: "
            "L2 L4 L8 L10."
        ),
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=64,
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
    )

    parser.add_argument(
        "--sheet-white-threshold",
        type=float,
        default=0.94,
    )

    parser.add_argument(
        "--thread-count",
        type=int,
        default=0,
        help="0 = automatic CPU detection.",
    )

    parser.add_argument(
        "--symmetry-x",
        action="store_true",
    )

    parser.add_argument(
        "--voxel-size",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--target-height",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--mesh-mode",
        choices=(
            "blocks",
            "surface_nets",
        ),
        default="blocks",
        help=(
            "Mesh extraction algorithm. "
            "blocks preserves the historical "
            "voxel-face mesher; surface_nets "
            "uses smooth Surface Nets extraction."
        ),
    )

    parser.add_argument(
        "--skip-blend",
        action="store_true",
    )

    parser.add_argument(
        "--json-log",
        action="store_true",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )


# ---------------------------------------------------------
# Discovery
# ---------------------------------------------------------

def discover_examples(
    examples_root: Path,
    requested_example: str,
) -> list[Path]:
    examples_root = (
        examples_root.resolve()
    )

    if not examples_root.exists():
        raise FileNotFoundError(
            (
                "Examples root does not exist: "
                f"{examples_root}"
            )
        )

    if requested_example != "all":
        example_dir = (
            examples_root
            / requested_example
        ).resolve()

        try:
            example_dir.relative_to(
                examples_root
            )

        except ValueError as exc:
            raise ValueError(
                (
                    "Requested example must be "
                    "inside the examples root."
                )
            ) from exc

        _validate_example_dir(
            example_dir
        )

        return [
            example_dir
        ]

    result = [
        sheets_dir.parent
        for sheets_dir
        in examples_root.rglob(
            "sheets"
        )
        if (
            sheets_dir.is_dir()
            and any(
                sheets_dir.glob(
                    "sheet*.png"
                )
            )
        )
    ]

    return sorted(
        result
    )


def _validate_example_dir(
    example_dir: Path,
) -> None:
    if not example_dir.exists():
        raise FileNotFoundError(
            (
                "Example does not exist: "
                f"{example_dir}"
            )
        )

    sheets_dir = (
        example_dir
        / "sheets"
    )

    if not sheets_dir.exists():
        raise FileNotFoundError(
            (
                "Missing sheets directory: "
                f"{sheets_dir}"
            )
        )

    if not any(
        sheets_dir.glob(
            "sheet*.png"
        )
    ):
        raise RuntimeError(
            (
                "No sheet*.png found in "
                f"{sheets_dir}"
            )
        )


def discover_sheets(
    example_dirs: list[Path],
) -> list[
    tuple[
        Path,
        Path,
    ]
]:
    sheets: list[
        tuple[
            Path,
            Path,
        ]
    ] = []

    for example_dir in example_dirs:
        for sheet_path in sorted(
            (
                example_dir
                / "sheets"
            ).glob(
                "sheet*.png"
            )
        ):
            sheets.append(
                (
                    example_dir,
                    sheet_path,
                )
            )

    return sheets


def filter_from_sheet(
    sheets: list[
        tuple[
            Path,
            Path,
        ]
    ],
    *,
    examples_root: Path,
    start_sheet: str,
) -> list[
    tuple[
        Path,
        Path,
    ]
]:
    if not start_sheet:
        return sheets

    normalized = (
        start_sheet
        .replace(
            "\\",
            "/",
        )
        .strip()
    )

    matches: list[int] = []

    for index, (
        _example_dir,
        sheet_path,
    ) in enumerate(
        sheets
    ):
        relative = (
            sheet_path
            .relative_to(
                examples_root
            )
            .as_posix()
        )

        if (
            relative == normalized
            or sheet_path.name
            == normalized
        ):
            matches.append(
                index
            )

    if not matches:
        available = "\n".join(
            (
                "  - "
                + sheet_path
                .relative_to(
                    examples_root
                )
                .as_posix()
            )
            for _, sheet_path
            in sheets
        )

        raise ValueError(
            (
                f'Could not find start sheet '
                f'"{start_sheet}".\n'
                f"Available sheets:\n"
                f"{available}"
            )
        )

    if len(matches) > 1:
        ambiguous = "\n".join(
            (
                "  - "
                + sheets[index][1]
                .relative_to(
                    examples_root
                )
                .as_posix()
            )
            for index in matches
        )

        raise ValueError(
            (
                f'Sheet "{start_sheet}" '
                "is ambiguous.\n"
                "Use a path relative to example/:\n"
                f"{ambiguous}"
            )
        )

    return sheets[
        matches[0]:
    ]


# ---------------------------------------------------------
# Normalization / validation
# ---------------------------------------------------------

def normalize_profiles(
    profiles: list[str] | None,
) -> list[str] | None:
    if not profiles:
        return None

    return [
        profile
        .strip()
        .upper()
        for profile in profiles
        if profile.strip()
    ]


def validate_numeric_args(
    args: argparse.Namespace,
) -> None:
    if not (
        8
        <= args.resolution
        <= 256
    ):
        raise ValueError(
            (
                "Resolution must be "
                "between 8 and 256."
            )
        )

    if not (
        0.0
        <= args.threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Threshold must be "
                "between 0 and 1."
            )
        )

    if not (
        0.0
        <= args.sheet_white_threshold
        <= 1.0
    ):
        raise ValueError(
            (
                "Sheet white threshold must be "
                "between 0 and 1."
            )
        )

    if args.thread_count < 0:
        raise ValueError(
            (
                "Thread count cannot "
                "be negative."
            )
        )

    if args.voxel_size <= 0.0:
        raise ValueError(
            (
                "Voxel size must be "
                "greater than zero."
            )
        )

    if args.target_height <= 0.0:
        raise ValueError(
            (
                "Target height must be "
                "greater than zero."
            )
        )


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


if __name__ == "__main__":
    main()