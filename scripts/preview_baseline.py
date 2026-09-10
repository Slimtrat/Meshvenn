from __future__ import annotations

import argparse
import hashlib
import json
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------

SCHEMA_VERSION = 1

DEFAULT_RENDERER_VERSION = 1

DEFAULT_OUTPUTS = {
    "geometry": "geometry.png",
    "material": "material.png",
    "turntable": "turntable.png",
}


# ---------------------------------------------------------
# Errors
# ---------------------------------------------------------

class BaselineError(RuntimeError):
    pass


# ---------------------------------------------------------
# Data
# ---------------------------------------------------------

@dataclass(frozen=True)
class BaselineConfig:
    resolution: int

    mesh_mode: str
    material_mode: str

    samples: int

    turntable_views: int
    render_size: int

    renderer_version: int = (
        DEFAULT_RENDERER_VERSION
    )

    def validate(self) -> None:
        if self.resolution <= 0:
            raise BaselineError(
                "resolution must be greater than zero."
            )

        if self.mesh_mode not in {
            "blocks",
            "surface_nets",
        }:
            raise BaselineError(
                (
                    "Unsupported mesh mode: "
                    f"{self.mesh_mode}"
                )
            )

        if not self.material_mode:
            raise BaselineError(
                "material_mode cannot be empty."
            )

        if self.samples <= 0:
            raise BaselineError(
                "samples must be greater than zero."
            )

        if self.turntable_views <= 0:
            raise BaselineError(
                (
                    "turntable_views must be "
                    "greater than zero."
                )
            )

        if self.render_size <= 0:
            raise BaselineError(
                (
                    "render_size must be "
                    "greater than zero."
                )
            )

        if self.renderer_version <= 0:
            raise BaselineError(
                (
                    "renderer_version must be "
                    "greater than zero."
                )
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()

        return {
            "resolution": self.resolution,
            "mesh_mode": self.mesh_mode,
            "material_mode": self.material_mode,
            "samples": self.samples,
            "turntable_views": (
                self.turntable_views
            ),
            "render_size": self.render_size,
            "renderer_version": (
                self.renderer_version
            ),
        }


@dataclass(frozen=True)
class CompatibilityResult:
    compatible: bool
    reason: str


# ---------------------------------------------------------
# Hashing
# ---------------------------------------------------------

def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


# ---------------------------------------------------------
# Path helpers
# ---------------------------------------------------------

def _repo_relative_path(
    path: Path,
    repo_root: Path,
) -> str:
    resolved_root = (
        repo_root.resolve()
    )

    resolved_path = (
        path.resolve()
    )

    try:
        relative = (
            resolved_path
            .relative_to(
                resolved_root
            )
        )

    except ValueError as exc:
        raise BaselineError(
            (
                f"{resolved_path} is outside "
                f"repository root "
                f"{resolved_root}."
            )
        ) from exc

    return relative.as_posix()


def _unique_names(
    values: list[str],
) -> list[str]:
    result: list[str] = []

    seen: set[str] = set()

    for raw_value in values:
        value = raw_value.strip()

        if not value:
            continue

        if value in seen:
            continue

        seen.add(
            value
        )

        result.append(
            value
        )

    return result


# ---------------------------------------------------------
# Manifest generation
# ---------------------------------------------------------

def build_manifest(
    *,
    repo_root: Path,
    sheets_dir: Path,
    sheet_names: list[str],
    profiles: list[str],
    config: BaselineConfig,
    source_commit: str,
) -> dict[str, Any]:
    config.validate()

    sheet_names = _unique_names(
        sheet_names
    )

    profiles = _unique_names(
        profiles
    )

    if not sheet_names:
        raise BaselineError(
            "At least one sheet is required."
        )

    if not profiles:
        raise BaselineError(
            "At least one profile is required."
        )

    if not source_commit.strip():
        raise BaselineError(
            "source_commit cannot be empty."
        )

    sheets: dict[
        str,
        dict[str, Any],
    ] = {}

    for sheet_name in sheet_names:
        sheet_path = (
            sheets_dir
            / f"{sheet_name}.png"
        )

        if not sheet_path.is_file():
            raise BaselineError(
                (
                    "Missing source sheet: "
                    f"{sheet_path}"
                )
            )

        sheets[
            sheet_name
        ] = {
            "source": (
                _repo_relative_path(
                    sheet_path,
                    repo_root,
                )
            ),
            "source_sha256": (
                sha256_file(
                    sheet_path
                )
            ),
        }

    return {
        "schema_version": (
            SCHEMA_VERSION
        ),
        "source_commit": (
            source_commit.strip()
        ),
        "configuration": (
            config.to_dict()
        ),
        "profiles": profiles,
        "outputs": dict(
            DEFAULT_OUTPUTS
        ),
        "sheets": sheets,
    }


def write_manifest(
    manifest: dict[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized = json.dumps(
        manifest,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    )

    output_path.write_text(
        serialized + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------

def load_manifest(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise BaselineError(
            (
                "Baseline manifest does "
                f"not exist: {path}"
            )
        )

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise BaselineError(
            (
                "Could not read baseline "
                f"manifest: {path}"
            )
        ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise BaselineError(
            (
                "Baseline manifest root "
                "must be an object."
            )
        )

    return data


# ---------------------------------------------------------
# Compatibility
# ---------------------------------------------------------

def check_compatibility(
    manifest: dict[str, Any],
    *,
    sheet_name: str,
    source_path: Path,
    profile: str,
    expected_config: BaselineConfig,
) -> CompatibilityResult:
    expected_config.validate()

    if (
        manifest.get(
            "schema_version"
        )
        != SCHEMA_VERSION
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                "schema-version-mismatch"
            ),
        )

    configuration = (
        manifest.get(
            "configuration"
        )
    )

    if not isinstance(
        configuration,
        dict,
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                "missing-configuration"
            ),
        )

    expected = (
        expected_config.to_dict()
    )

    for (
        key,
        expected_value,
    ) in expected.items():
        actual_value = (
            configuration.get(
                key
            )
        )

        if (
            actual_value
            != expected_value
        ):
            return CompatibilityResult(
                compatible=False,
                reason=(
                    "configuration-mismatch:"
                    f"{key}:"
                    f"{actual_value}"
                    "!="
                    f"{expected_value}"
                ),
            )

    profiles = (
        manifest.get(
            "profiles"
        )
    )

    if (
        not isinstance(
            profiles,
            list,
        )
        or profile
        not in profiles
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                f"profile-missing:{profile}"
            ),
        )

    sheets = (
        manifest.get(
            "sheets"
        )
    )

    if not isinstance(
        sheets,
        dict,
    ):
        return CompatibilityResult(
            compatible=False,
            reason="missing-sheets",
        )

    sheet = sheets.get(
        sheet_name
    )

    if not isinstance(
        sheet,
        dict,
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                f"sheet-missing:{sheet_name}"
            ),
        )

    if not source_path.is_file():
        return CompatibilityResult(
            compatible=False,
            reason=(
                "source-sheet-missing:"
                f"{source_path}"
            ),
        )

    expected_source_hash = (
        sheet.get(
            "source_sha256"
        )
    )

    current_source_hash = (
        sha256_file(
            source_path
        )
    )

    if (
        expected_source_hash
        != current_source_hash
    ):
        return CompatibilityResult(
            compatible=False,
            reason=(
                "source-hash-mismatch"
            ),
        )

    outputs = (
        manifest.get(
            "outputs"
        )
    )

    if not isinstance(
        outputs,
        dict,
    ):
        return CompatibilityResult(
            compatible=False,
            reason="missing-outputs",
        )

    for (
        output_name,
        expected_filename,
    ) in DEFAULT_OUTPUTS.items():
        if (
            outputs.get(
                output_name
            )
            != expected_filename
        ):
            return CompatibilityResult(
                compatible=False,
                reason=(
                    "output-layout-mismatch:"
                    f"{output_name}"
                ),
            )

    return CompatibilityResult(
        compatible=True,
        reason="compatible",
    )


# ---------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------

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


if __name__ == "__main__":
    raise SystemExit(
        main()
    )