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
    )

    parser.add_argument(
        "--examples",
        type=Path,
        default=REPO_ROOT / "example",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "output",
    )

    parser.add_argument(
        "--resolution",
        type=int,
        default=64,
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
    )

    return parser.parse_args()


def discover_examples(root: Path) -> list[Path]:
    results = []

    for sheets_dir in root.rglob("sheets"):
        if not sheets_dir.is_dir():
            continue

        if any(sheets_dir.glob("sheet*.png")):
            results.append(sheets_dir.parent)

    return sorted(results)


def main() -> None:
    args = parse_args()

    examples_root = args.examples.resolve()
    output_root = args.output.resolve()

    examples = discover_examples(examples_root)

    if not examples:
        raise SystemExit(
            f"No example/*/sheets/sheet*.png found under {examples_root}"
        )

    failures = []

    for example_dir in examples:
        relative = example_dir.relative_to(examples_root)
        output_dir = output_root / relative

        command = [
            args.blender,
            "--background",
            "--factory-startup",
            "--python",
            str((REPO_ROOT / "scripts" / "generate_example.py").resolve()),
            "--",
            str(example_dir),
            str(output_dir),
            "--resolution",
            str(args.resolution),
        ]

        print()
        print("=" * 80)
        print(f"[projection-tool] EXAMPLE {relative}")
        print("=" * 80)

        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
        )

        if completed.returncode != 0:
            failures.append(relative)

            if not args.continue_on_error:
                break

    if failures:
        print("Failed examples:")

        for failure in failures:
            print(f"  - {failure}")

        raise SystemExit(1)


if __name__ == "__main__":
    main()
