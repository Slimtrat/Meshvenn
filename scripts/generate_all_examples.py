from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate all Projection Tool examples with Blender headless."
    )
    parser.add_argument(
        "--blender",
        default="blender",
        help="Blender executable path (default: blender)",
    )
    parser.add_argument(
        "--examples",
        type=Path,
        default=REPO_ROOT / "example",
        help="Examples root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "output",
        help="Generated output root",
    )
    parser.add_argument("--resolution", type=int, default=64)
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--voxel-size", type=float, default=0.05)
    parser.add_argument("--smooth", type=int, default=3)
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue generating remaining examples after a failure",
    )
    return parser.parse_args()


def find_example_dirs(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Examples root does not exist: {root}")

    dirs = []
    for directory in root.rglob("*"):
        if not directory.is_dir():
            continue

        images = [
            path for path in directory.iterdir()
            if path.is_file()
            and path.suffix.lower() in {
                ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"
            }
        ]
        if len(images) >= 2:
            dirs.append(directory)

    return sorted(dirs)


def run_example(args: argparse.Namespace, example_dir: Path) -> int:
    relative = example_dir.relative_to(args.examples.resolve())
    output_dir = args.output.resolve() / relative

    command = [
        args.blender,
        "--background",
        "--factory-startup",
        "--python",
        str((REPO_ROOT / "scripts" / "generate_example.py").resolve()),
        "--",
        str(example_dir.resolve()),
        str(output_dir),
        "--resolution",
        str(args.resolution),
        "--threshold",
        str(args.threshold),
        "--voxel-size",
        str(args.voxel_size),
        "--smooth",
        str(args.smooth),
    ]

    print()
    print("=" * 80)
    print(f"[projection-tool] {relative}")
    print("=" * 80)

    completed = subprocess.run(command, cwd=REPO_ROOT)
    return completed.returncode


def main() -> None:
    args = parse_args()
    args.examples = args.examples.resolve()
    args.output = args.output.resolve()

    example_dirs = find_example_dirs(args.examples)

    if not example_dirs:
        print(f"No examples found under {args.examples}")
        raise SystemExit(2)

    failures = []

    for example_dir in example_dirs:
        result = run_example(args, example_dir)

        if result != 0:
            failures.append(example_dir)

            if not args.continue_on_error:
                break

    print()
    print(f"Generated: {len(example_dirs) - len(failures)}")
    print(f"Failed:    {len(failures)}")

    if failures:
        print("Failures:")
        for path in failures:
            print(f"  - {path.relative_to(args.examples)}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
