"""Hard-bounded caller's child: exercise a genuine, safe DLL API rejection."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main() -> int:
    from core.native_bridge import NativeCore, NativeCoreError
    try:
        core = NativeCore(library_path=Path(sys.argv[1]))
        # Native bpt_visual_hull_create validates resolution before allocation.
        with core.create_session(resolution=0):
            pass
    except NativeCoreError as exc:
        print(json.dumps({"state": "native_rejected", "dll_api_executed": True,
                          "native_error_code": exc.code, "message": str(exc),
                          "geometry_quality_evaluated": False}))
        return 0
    except (OSError, RuntimeError) as exc:
        print(json.dumps({"state": "native_unavailable", "dll_api_executed": False,
                          "error_type": type(exc).__name__, "geometry_quality_evaluated": False}))
        return 1
    print(json.dumps({"state": "unexpected_native_success", "dll_api_executed": True,
                      "geometry_quality_evaluated": False}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
