import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from blender_uv_bake_smoke_support.runner import main
except Exception:
    traceback.print_exc()
    raise SystemExit(1)


if __name__ == "__main__":
    main()
