from __future__ import annotations

from ...core.native_loader import (
    EXPECTED_ABI_VERSION,
    NativeAbiMismatchError,
    NativeLibraryLoadError,
    NativeLibraryNotFoundError,
    find_native_library,
    load_native_library,
)
from ...core.pipeline_contracts import ImplementationAvailability


def _native_library_availability() -> ImplementationAvailability:
    """
    Validate both presence and ABI of the native library.

    This gives the general pipeline UI a useful READY /
    UNAVAILABLE state without knowing anything about ctypes.
    """
    try:
        path = find_native_library()
        library = load_native_library(path)
        abi_version = int(library.bpt_abi_version())
    except NativeLibraryNotFoundError as exc:
        return ImplementationAvailability.unavailable(
            "Native C++ library not found.", details={"error": str(exc)}
        )
    except NativeAbiMismatchError as exc:
        return ImplementationAvailability.unavailable(
            "Native C++ ABI mismatch.",
            details={"expected_abi": EXPECTED_ABI_VERSION, "error": str(exc)},
        )
    except NativeLibraryLoadError as exc:
        return ImplementationAvailability.unavailable(
            "Native C++ library could not be loaded.", details={"error": str(exc)}
        )
    except Exception as exc:
        return ImplementationAvailability.unavailable(
            "Native C++ engine availability check failed.",
            details={"exception_type": type(exc).__name__, "error": str(exc)},
        )
    return ImplementationAvailability.ready_state(
        details={"library": str(path), "abi": abi_version}
    )
