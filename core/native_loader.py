from __future__ import annotations

import ctypes
import platform
from pathlib import Path


class NativeLibraryNotFoundError(RuntimeError):
    pass


class NativeLibraryLoadError(RuntimeError):
    pass


class NativeAbiMismatchError(RuntimeError):
    pass


EXPECTED_ABI_VERSION = 1


def _library_filename() -> str:
    system = platform.system().lower()

    if system == "windows":
        return "bpt_core.dll"

    if system == "darwin":
        return "libbpt_core.dylib"

    return "libbpt_core.so"


def _candidate_paths() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    filename = _library_filename()

    candidates = [
        root / "native" / "bin" / filename,
        root / "native" / filename,
        root / filename,
    ]

    # Local development / CMake output.
    candidates.extend(
        [
            root / "build" / "native" / filename,
            root / "build" / "native" / "Release" / filename,
            root / "build" / "native" / "Debug" / filename,
        ]
    )

    return candidates


def find_native_library() -> Path:
    candidates = _candidate_paths()

    for path in candidates:
        if path.is_file():
            return path

    formatted = "\n".join(
        f"  - {path}"
        for path in candidates
    )

    raise NativeLibraryNotFoundError(
        "Could not find Blender Projection Tool native library.\n"
        f"Expected one of:\n{formatted}"
    )


def load_native_library(
    path: Path | None = None,
) -> ctypes.CDLL:
    library_path = (
        path.resolve()
        if path is not None
        else find_native_library().resolve()
    )

    try:
        library = ctypes.CDLL(
            str(library_path)
        )
    except OSError as exc:
        raise NativeLibraryLoadError(
            "Failed to load native Blender Projection Tool library:\n"
            f"{library_path}\n"
            f"{exc}"
        ) from exc

    try:
        library.bpt_abi_version.argtypes = []
        library.bpt_abi_version.restype = ctypes.c_uint32

        actual_abi = int(
            library.bpt_abi_version()
        )
    except Exception as exc:
        raise NativeLibraryLoadError(
            "Native library loaded, but bpt_abi_version() "
            "could not be called."
        ) from exc

    if actual_abi != EXPECTED_ABI_VERSION:
        raise NativeAbiMismatchError(
            "Native ABI mismatch.\n"
            f"Expected: {EXPECTED_ABI_VERSION}\n"
            f"Actual:   {actual_abi}\n"
            f"Library:  {library_path}"
        )

    return library