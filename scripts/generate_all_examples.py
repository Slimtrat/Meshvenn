from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate all Projection Tool examples."
    )

    parser.add_argument(
        "--blender",
        default="blender",
        help="Blender executable path.",
    )

    parser.add_argument(
        "--examples",
        type=Path,
        default=REPO_ROOT / "example",
        help="Examples root directory.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "output",
        help="Output root directory.",
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
        "--profiles",
        nargs="*",
        default=None,
        help="Optional profiles, e.g. L2 L4 L8 L10.",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args()


def discover_examples(
    root: Path,
) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(
            f"Examples root does not exist: {root}"
        )

    results: list[Path] = []

    for sheets_dir in root.rglob("sheets"):
        if not sheets_dir.is_dir():
            continue

        if any(sheets_dir.glob("sheet*.png")):
            results.append(
                sheets_dir.parent
            )

    return sorted(
        results
    )


def build_command(
    args: argparse.Namespace,
    example_dir: Path,
    output_dir: Path,
) -> list[str]:
    command = [
        args.blender,
        "--background",
        "--factory-startup",
        "--python",
        str(
            (
                REPO_ROOT
                / "scripts"
                / "generate_example.py"
            ).resolve()
        ),
        "--",
        str(example_dir.resolve()),
        str(output_dir.resolve()),
        "--resolution",
        str(args.resolution),
        "--threshold",
        str(args.threshold),
        "--target-height",
        str(args.target_height),
        "--voxel-size",
        str(args.voxel_size),
        "--smooth",
        str(args.smooth),
        "--sheet-white-threshold",
        str(args.sheet_white_threshold),
    ]

    if args.symmetry_x:
        command.append(
            "--symmetry-x"
        )

    if args.no_remesh:
        command.append(
            "--no-remesh"
        )

    if args.profiles:
        command.append(
            "--profiles"
        )

        command.extend(
            args.profiles
        )

    return command


def run_example(
    args: argparse.Namespace,
    example_dir: Path,
) -> int:
    relative = example_dir.relative_to(
        args.examples
    )

    output_dir = (
        args.output
        / relative
    )

    command = build_command(
        args,
        example_dir,
        output_dir,
    )

    print()
    print("=" * 80)
    print(
        f"[projection-tool] EXAMPLE {relative}"
    )
    print("=" * 80)

    print(
        "[projection-tool] command:"
    )

    print(
        " ".join(
            str(part)
            for part in command
        )
    )

    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
    )

    return completed.returncode


def main() -> None:
    args = parse_args()

    args.examples = args.examples.resolve()
    args.output = args.output.resolve()

    examples = discover_examples(
        args.examples
    )

    if not examples:
        raise SystemExit(
            "No example directories containing "
            "sheets/sheet*.png were found under "
            f"{args.examples}"
        )

    print(
        f"[projection-tool] "
        f"detected {len(examples)} example(s)"
    )

    failures: list[Path] = []

    for example_dir in examples:
        return_code = run_example(
            args,
            example_dir,
        )

        if return_code == 0:
            continue

        failures.append(
            example_dir
        )

        if not args.continue_on_error:
            break

    generated_count = (
        len(examples)
        - len(failures)
    )

    print()
    print("=" * 80)
    print(
        f"[projection-tool] generated: "
        f"{generated_count}"
    )
    print(
        f"[projection-tool] failed: "
        f"{len(failures)}"
    )

    if failures:
        print(
            "[projection-tool] failures:"
        )

        for example_dir in failures:
            print(
                "  - "
                + str(
                    example_dir.relative_to(
                        args.examples
                    )
                )
            )

        raise SystemExit(1)


if __name__ == "__main__":
    main()