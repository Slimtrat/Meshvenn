"""Generate actual source/current/fine character comparisons; no paid provider."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory; previous evidence is never overwritten.")
    parser.add_argument("--blender", type=Path, default=os.environ.get("MESHVENN_TEST_BLENDER"), required=not bool(os.environ.get("MESHVENN_TEST_BLENDER")))
    parser.add_argument("--native-library", type=Path, default=os.environ.get("MESHVENN_TEST_NATIVE_LIBRARY"))
    parser.add_argument("--source-glb", type=Path)
    parser.add_argument("--from-reconstruction", type=Path, action="append", default=[], help="Inspect cached actual reconstruction manifests; each GLB is reimported and verified again.")
    parser.add_argument("--standard-only", action="store_true")
    parser.add_argument("--render-size", type=int, default=640)
    options = parser.parse_args(argv)
    from scripts.character_quality.workflow import qualify_characters
    try:
        result = qualify_characters(options.output, blender_executable=options.blender,
            native_library=options.native_library, source_glb=options.source_glb,
            from_reconstruction=options.from_reconstruction, include_high_resolution=not options.standard_only,
            render_size=options.render_size)
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        print("Character comparison unavailable: " + str(exc), file=sys.stderr)
        return 1
    print("Actual character comparison completed: " + str(result["candidate_count"]) + " candidates.")
    print("Review: " + str(options.output / result["review_page"]["path"]))
    print("Visual/identity/animation qualification remains UNKNOWN; coarse geometry scores are not aesthetic approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
