from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import BaselineConfig, BaselineError, DEFAULT_OUTPUTS, SCHEMA_VERSION

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
