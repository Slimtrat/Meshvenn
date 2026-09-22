from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .models import BaselineConfig, BaselineError, DEFAULT_RENDERER_VERSION
from .manifest import build_manifest, load_manifest, write_manifest
from .compatibility import check_compatibility

def _add_config_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--resolution",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--mesh-mode",
        choices=(
            "blocks",
            "surface_nets",
        ),
        required=True,
    )

    parser.add_argument(
        "--material-mode",
        required=True,
    )

    parser.add_argument(
        "--samples",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--turntable-views",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--render-size",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--renderer-version",
        type=int,
        default=(
            DEFAULT_RENDERER_VERSION
        ),
    )


def _config_from_args(
    args: argparse.Namespace,
) -> BaselineConfig:
    return BaselineConfig(
        resolution=(
            args.resolution
        ),
        mesh_mode=(
            args.mesh_mode
        ),
        material_mode=(
            args.material_mode
        ),
        samples=(
            args.samples
        ),
        turntable_views=(
            args.turntable_views
        ),
        render_size=(
            args.render_size
        ),
        renderer_version=(
            args.renderer_version
        ),
    )


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def parse_args(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create and validate persistent "
            "visual-preview baseline metadata."
        )
    )

    subparsers = (
        parser.add_subparsers(
            dest="command",
            required=True,
        )
    )

    # -----------------------------------------------------
    # write
    # -----------------------------------------------------

    write_parser = (
        subparsers.add_parser(
            "write",
            help=(
                "Write a deterministic "
                "baseline manifest."
            ),
        )
    )

    write_parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
    )

    write_parser.add_argument(
        "--sheets-dir",
        type=Path,
        required=True,
    )

    write_parser.add_argument(
        "--sheet-names",
        nargs="+",
        required=True,
    )

    write_parser.add_argument(
        "--profiles",
        nargs="+",
        required=True,
    )

    write_parser.add_argument(
        "--source-commit",
        required=True,
    )

    write_parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    _add_config_arguments(
        write_parser
    )

    # -----------------------------------------------------
    # check
    # -----------------------------------------------------

    check_parser = (
        subparsers.add_parser(
            "check",
            help=(
                "Check whether a persisted "
                "baseline can be reused."
            ),
        )
    )

    check_parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
    )

    check_parser.add_argument(
        "--sheet",
        required=True,
    )

    check_parser.add_argument(
        "--source",
        type=Path,
        required=True,
    )

    check_parser.add_argument(
        "--profile",
        required=True,
    )

    _add_config_arguments(
        check_parser
    )

    return parser.parse_args(
        argv
    )


# ---------------------------------------------------------
# Commands
# ---------------------------------------------------------

def _command_write(
    args: argparse.Namespace,
) -> int:
    config = (
        _config_from_args(
            args
        )
    )

    manifest = build_manifest(
        repo_root=(
            args.repo_root
        ),
        sheets_dir=(
            args.sheets_dir
        ),
        sheet_names=(
            args.sheet_names
        ),
        profiles=(
            args.profiles
        ),
        config=config,
        source_commit=(
            args.source_commit
        ),
    )

    write_manifest(
        manifest,
        args.output,
    )

    print(
        (
            "Visual baseline manifest "
            f"written: {args.output}"
        )
    )

    return 0


def _command_check(
    args: argparse.Namespace,
) -> int:
    try:
        manifest = load_manifest(
            args.manifest
        )

    except BaselineError as exc:
        print(
            (
                "incompatible: "
                f"{exc}"
            ),
            file=sys.stderr,
        )

        return 1

    config = (
        _config_from_args(
            args
        )
    )

    result = (
        check_compatibility(
            manifest,
            sheet_name=(
                args.sheet
            ),
            source_path=(
                args.source
            ),
            profile=(
                args.profile
            ),
            expected_config=(
                config
            ),
        )
    )

    prefix = (
        "compatible"
        if result.compatible
        else "incompatible"
    )

    print(
        (
            f"{prefix}: "
            f"{args.sheet}/"
            f"{args.profile}: "
            f"{result.reason}"
        )
    )

    return (
        0
        if result.compatible
        else 1
    )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main(
    argv: list[str] | None = None,
) -> int:
    args = parse_args(
        argv
    )

    try:
        if (
            args.command
            == "write"
        ):
            return _command_write(
                args
            )

        if (
            args.command
            == "check"
        ):
            return _command_check(
                args
            )

        raise BaselineError(
            (
                "Unknown command: "
                f"{args.command}"
            )
        )

    except BaselineError as exc:
        print(
            f"error: {exc}",
            file=sys.stderr,
        )

        return 2
