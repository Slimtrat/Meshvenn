# version.py

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_extension_version() -> str:
    manifest_path = Path(__file__).resolve().parent / "blender_manifest.toml"

    try:
        with manifest_path.open("rb") as manifest_file:
            manifest = tomllib.load(manifest_file)

        return str(
            manifest.get(
                "version",
                "unknown",
            )
        )

    except Exception:
        return "unknown"


def get_version_label() -> str:
    return f"v{get_extension_version()}"