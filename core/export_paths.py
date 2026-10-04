"""Filesystem-only export guards, shared by planning and publication."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def protect_source_paths(destination: Path, sources: Iterable[Path]) -> None:
    """Reject lexical, symlink-parent and hard-link aliases of an input."""
    if destination.is_symlink():
        raise ValueError("GLB export output cannot be a symbolic link.")
    resolved = destination.resolve(strict=False)
    for source in sources:
        source = Path(source).expanduser().resolve(strict=False)
        same_path = os.path.normcase(str(resolved)) == os.path.normcase(str(source))
        same_file = destination.exists() and source.exists() and destination.samefile(source)
        if same_path or same_file:
            raise ValueError(f"GLB export output cannot overwrite its source file: {source}")


def resolve_export_path(value, overwrite: bool, *, sources: Iterable[Path] = ()) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise TypeError('Pipeline metadata must define "export_output_path" as a path.') from exc
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError('Pipeline metadata must define "export_output_path".')
    if not isinstance(overwrite, bool):
        raise TypeError('Pipeline metadata "export_overwrite_existing" must be boolean.')
    # Do not dereference the final symlink before checking it.
    path = Path(os.path.abspath(Path(raw).expanduser()))
    if path.suffix.lower() != ".glb":
        raise ValueError("GLB export output must use the .glb extension.")
    protect_source_paths(path, sources)
    if path.exists() and not path.is_file():
        raise ValueError(f"GLB export output is not a regular file: {path}")
    if path.exists() and not overwrite:
        raise FileExistsError(f"GLB export output already exists; enable overwrite to replace it: {path}")
    if path.parent.exists() and not path.parent.is_dir():
        raise ValueError(f"GLB export parent is not a directory: {path.parent}")
    return path
