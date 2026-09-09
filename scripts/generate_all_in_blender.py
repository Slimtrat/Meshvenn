from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from scripts.generate_example import process_sheet


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
            "Generate Projection Tool examples "
            "inside a single Blender process."
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
            'Example relative path such as "mascotte/test1", '
            'or "all".'
        ),
    )

    parser.add_argument(
        "--start-sheet",
        default="",
        help=(
            "Start generation from this sheet. "
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
        "--target-height",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--voxel-size",
        type=float,
        default=0.05,
    )

    parser.add_argument(
        "--smooth",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--sheet-white-threshold",
        type=float,
        default=0.94,
    )

    parser.add_argument(
        "--symmetry-x",
        action="store_true",
    )

    parser.add_argument(
        "--no-remesh",
        action="store_true",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args(
        argv
    )


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

        try:
            example_dir.relative_to(
                examples_root.resolve()
            )
        except ValueError as exc:
            raise ValueError(
                "Example must be inside the example root."
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
) -> list[tuple[Path, Path]]:
    result: list[
        tuple[Path, Path]
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
        tuple[Path, Path]
    ],
    examples_root: Path,
    start_sheet: str,
) -> list[
    tuple[Path, Path]
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
    ) in enumerate(sheets):
        relative = (
            sheet_path
            .relative_to(
                examples_root
            )
            .as_posix()
        )

        if (
            relative == normalized
            or sheet_path.name == normalized
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
            for _, sheet_path in sheets
        )

        raise ValueError(
            f'Could not find start sheet "{start_sheet}".\n'
            f"Available sheets:\n{available}"
        )

    if len(matches) > 1:
        matching_paths = "\n".join(
            "  - "
            + sheets[index][1]
            .relative_to(
                examples_root
            )
            .as_posix()
            for index in matches
        )

        raise ValueError(
            f'Sheet name "{start_sheet}" is ambiguous.\n'
            "Use its path relative to example/:\n"
            f"{matching_paths}"
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

    normalized = [
        profile.upper()
        for profile in profiles
    ]

    invalid = [
        profile
        for profile in normalized
        if profile not in allowed
    ]

    if invalid:
        raise ValueError(
            "Unknown profiles: "
            + ", ".join(
                invalid
            )
        )

    return normalized


def create_process_args(
    args: argparse.Namespace,
) -> argparse.Namespace:
    process_args = argparse.Namespace()

    process_args.resolution = (
        args.resolution
    )

    process_args.threshold = (
        args.threshold
    )

    process_args.target_height = (
        args.target_height
    )

    process_args.voxel_size = (
        args.voxel_size
    )

    process_args.smooth = (
        args.smooth
    )

    process_args.symmetry_x = (
        args.symmetry_x
    )

    process_args.no_remesh = (
        args.no_remesh
    )

    process_args.sheet_white_threshold = (
        args.sheet_white_threshold
    )

    process_args.profiles = (
        validate_profiles(
            args.profiles
        )
    )

    return process_args


def print_plan(
    sheets: list[
        tuple[Path, Path]
    ],
    examples_root: Path,
    args: argparse.Namespace,
) -> None:
    print()
    print("=" * 80)
    print(
        "[projection-tool] "
        "GENERATION PLAN"
    )
    print("=" * 80)

    print(
        f"Resolution: {args.resolution}"
    )

    print(
        "Profiles: "
        + (
            ", ".join(
                args.profiles
            )
            if args.profiles
            else "automatic"
        )
    )

    print(
        f"Sheets: {len(sheets)}"
    )

    for _example_dir, sheet in sheets:
        print(
            "  - "
            + sheet
            .relative_to(
                examples_root
            )
            .as_posix()
        )


def main() -> None:
    args = parse_args()

    examples_root = (
        args.examples
        .resolve()
    )

    args.profiles = (
        validate_profiles(
            args.profiles
        )
    )

    example_dirs = discover_examples(
        examples_root,
        args.example,
    )

    sheets = discover_sheets(
        example_dirs
    )

    if not sheets:
        raise RuntimeError(
            "No sheet*.png found."
        )

    sheets = filter_from_sheet(
        sheets,
        examples_root,
        args.start_sheet,
    )

    if not sheets:
        raise RuntimeError(
            "No sheets remain after filtering."
        )

    print_plan(
        sheets,
        examples_root,
        args,
    )

    process_args = (
        create_process_args(
            args
        )
    )

    failures: list[
        tuple[Path, Exception]
    ] = []

    for (
        example_dir,
        sheet_path,
    ) in sheets:
        relative_sheet = (
            sheet_path
            .relative_to(
                examples_root
            )
            .as_posix()
        )

        print()
        print("=" * 80)
        print(
            "[projection-tool] "
            f"PROCESS {relative_sheet}"
        )
        print("=" * 80)

        try:
            generated_root = (
                example_dir
                / "generated"
            )

            process_sheet(
                sheet_path,
                generated_root,
                process_args,
            )

        except Exception as exc:
            failures.append(
                (
                    sheet_path,
                    exc,
                )
            )

            print(
                "[projection-tool] "
                f"FAILED {relative_sheet}: "
                f"{exc}"
            )

            if not args.continue_on_error:
                raise

    print()
    print("=" * 80)
    print(
        "[projection-tool] "
        "GENERATION SUMMARY"
    )
    print("=" * 80)

    print(
        f"Processed: {len(sheets)}"
    )

    print(
        f"Failed: {len(failures)}"
    )

    if failures:
        for sheet_path, exc in failures:
            print(
                "  - "
                + sheet_path
                .relative_to(
                    examples_root
                )
                .as_posix()
                + ": "
                + str(exc)
            )

        raise SystemExit(1)


if __name__ == "__main__":
    main()