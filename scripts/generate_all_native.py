from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_example_native import process_sheet
from scripts.run_logger import RunLogger


def parse_args() -> argparse.Namespace:
    argv = sys.argv

    if "--" in argv:
        argv = argv[
            argv.index("--") + 1 :
        ]
    else:
        argv = []

    parser = argparse.ArgumentParser(
        description=(
            "Generate all Projection Tool examples "
            "using the native C++ engine inside "
            "a single Blender process."
        )
    )

    parser.add_argument(
        "--examples",
        type=Path,
        default=REPO_ROOT / "example",
        help="Root example directory.",
    )

    parser.add_argument(
        "--example",
        default="all",
        help=(
            'Example relative path, e.g. "mascotte/test1", '
            'or "all".'
        ),
    )

    parser.add_argument(
        "--start-sheet",
        default="",
        help=(
            "Start from this sheet. "
            'Examples: "sheet2.png" or '
            '"mascotte/test1/sheets/sheet2.png".'
        ),
    )

    parser.add_argument(
        "--profiles",
        nargs="*",
        default=None,
        help="Profiles to generate: L2 L4 L8 L10.",
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
        help="0 = native auto detection.",
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

    return parser.parse_args(argv)


def discover_examples(
    examples_root: Path,
    requested_example: str,
) -> list[Path]:
    if not examples_root.exists():
        raise FileNotFoundError(
            f"Examples root does not exist: {examples_root}"
        )

    if requested_example != "all":
        example_dir = (
            examples_root
            / requested_example
        ).resolve()

        root = examples_root.resolve()

        try:
            example_dir.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "Requested example must be inside the examples root."
            ) from exc

        if not example_dir.exists():
            raise FileNotFoundError(
                f"Example does not exist: {example_dir}"
            )

        sheets_dir = (
            example_dir
            / "sheets"
        )

        if not sheets_dir.exists():
            raise FileNotFoundError(
                f"Missing sheets directory: {sheets_dir}"
            )

        if not any(
            sheets_dir.glob(
                "sheet*.png"
            )
        ):
            raise RuntimeError(
                f"No sheet*.png found in {sheets_dir}"
            )

        return [
            example_dir
        ]

    result: list[Path] = []

    for sheets_dir in examples_root.rglob(
        "sheets"
    ):
        if not sheets_dir.is_dir():
            continue

        if any(
            sheets_dir.glob(
                "sheet*.png"
            )
        ):
            result.append(
                sheets_dir.parent
            )

    return sorted(
        result
    )


def discover_sheets(
    example_dirs: list[Path],
) -> list[
    tuple[
        Path,
        Path,
    ]
]:
    result: list[
        tuple[
            Path,
            Path,
        ]
    ] = []

    for example_dir in example_dirs:
        sheets_dir = (
            example_dir
            / "sheets"
        )

        for sheet_path in sorted(
            sheets_dir.glob(
                "sheet*.png"
            )
        ):
            result.append(
                (
                    example_dir,
                    sheet_path,
                )
            )

    return result


def filter_from_sheet(
    sheets: list[
        tuple[
            Path,
            Path,
        ]
    ],
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
        .replace("\\", "/")
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
            "  - "
            + sheet_path
            .relative_to(
                examples_root
            )
            .as_posix()
            for _, sheet_path
            in sheets
        )

        raise ValueError(
            f'Could not find start sheet "{start_sheet}".\n'
            f"Available sheets:\n{available}"
        )

    if len(matches) > 1:
        available = "\n".join(
            "  - "
            + sheets[index][1]
            .relative_to(
                examples_root
            )
            .as_posix()
            for index
            in matches
        )

        raise ValueError(
            f'Sheet "{start_sheet}" is ambiguous.\n'
            "Use a path relative to example/:\n"
            f"{available}"
        )

    return sheets[
        matches[0] :
    ]


def validate_profiles(
    profiles: list[str] | None,
) -> list[str] | None:
    if not profiles:
        return None

    allowed = {
        "L2",
        "L4",
        "L8",
        "L10",
    }

    normalized: list[str] = []

    for profile in profiles:
        name = (
            profile
            .upper()
            .strip()
        )

        if name not in allowed:
            raise ValueError(
                f"Unknown profile: {profile}"
            )

        if name not in normalized:
            normalized.append(
                name
            )

    return normalized


def create_sheet_args(
    args: argparse.Namespace,
) -> argparse.Namespace:
    result = argparse.Namespace()

    result.resolution = (
        args.resolution
    )

    result.threshold = (
        args.threshold
    )

    result.sheet_white_threshold = (
        args.sheet_white_threshold
    )

    result.thread_count = (
        args.thread_count
    )

    result.symmetry_x = (
        args.symmetry_x
    )

    result.voxel_size = (
        args.voxel_size
    )

    result.target_height = (
        args.target_height
    )

    result.profiles = (
        validate_profiles(
            args.profiles
        )
    )

    result.skip_blend = (
        args.skip_blend
    )

    result.json_log = (
        args.json_log
    )

    return result


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
        value=args.resolution,
    )

    logger.info(
        "Profiles",
        value=(
            ", ".join(
                args.profiles
            )
            if args.profiles
            else "automatic"
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
            sheet_path
            .relative_to(
                examples_root
            )
            .as_posix(),
        )


def main() -> None:
    args = parse_args()

    examples_root = (
        args
        .examples
        .resolve()
    )

    args.profiles = (
        validate_profiles(
            args.profiles
        )
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

    sheets = (
        filter_from_sheet(
            sheets,
            examples_root,
            args.start_sheet,
        )
    )

    if not sheets:
        raise RuntimeError(
            "No sheets remain after filtering."
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

    sheet_args = (
        create_sheet_args(
            args
        )
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
                sheet_args,
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
                f"FAILED {relative_sheet}",
                error=str(
                    exc
                ),
            )

            if not args.continue_on_error:
                raise

    logger.divider(
        "NATIVE GENERATION SUMMARY"
    )

    logger.info(
        "Processed",
        count=total,
    )

    logger.info(
        "Succeeded",
        count=(
            total
            - len(
                failures
            )
        ),
    )

    logger.info(
        "Failed",
        count=len(
            failures
        ),
    )

    for (
        sheet_path,
        error,
    ) in failures:
        logger.error(
            sheet_path
            .relative_to(
                examples_root
            )
            .as_posix(),
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
            logger
            .total_elapsed()
        ),
    )


if __name__ == "__main__":
    main()