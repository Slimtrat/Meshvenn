"""Checkout convenience entry point for the installed-style Blender worker."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/meshvenn_humanoid/src"))
from meshvenn_humanoid.blender.worker import main

if __name__ == "__main__":
    if "--" not in sys.argv:
        sys.argv.append("--")
    sys.argv.extend(("--engine-root", str(ROOT)))
    raise SystemExit(main())
