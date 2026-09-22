"""Blender self-check for the V2 3D metric before scoring reconstructions."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.glb_v2_surface_metrics import compare_glb_surfaces


def main() -> None:
    assets = REPO_ROOT / "example" / "v2" / "assets"
    avocado = assets / "Avocado.glb"
    same = compare_glb_surfaces(avocado, avocado, samples=512)
    different = compare_glb_surfaces(avocado, assets / "BoomBox.glb", samples=512)
    if same["surface_fscore"] != 1.0 or same["symmetric_chamfer_mean"] > 1e-7:
        raise AssertionError("Identical GLB surfaces must score as identical")
    if different["surface_fscore"] >= 0.25:
        raise AssertionError("Unrelated GLB surfaces scored as a match")
    print(f"V2 3D metric self-check: identical={same['surface_fscore']:.3f}, "
          f"different={different['surface_fscore']:.3f}")


if __name__ == "__main__":
    main()
