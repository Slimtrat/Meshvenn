"""Offline real-native D3 qualification. No Blender, credentials or network."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "tests/fixtures/diagnostics/geometry-v1")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/geometry-diagnostic-qualification")
    parser.add_argument("--native-library", type=Path, help="Explicit existing native binary. Required for evaluation; never copied or modified.")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--regenerate", action="store_true", help="Explicitly regenerate the versioned original analytic fixtures")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--split", choices=("all", "calibration", "heldout"), default="all")
    parser.add_argument("--quick", action="store_true", help="Baseline only; cannot qualify the complete matrix")
    options = parser.parse_args(argv)
    if options.regenerate:
        from scripts.geometry_diagnostic_corpus.fixtures import build_corpus
        build_corpus(options.corpus)
    try:
        from scripts.geometry_diagnostic_corpus.runner import load_manifest, run_qualification
        if options.verify_only:
            manifest, digest = load_manifest(options.corpus)
            print(f"Verified {len(manifest['cases'])} frozen D3 cases, manifest {digest}. No native quality evaluation executed.")
            return 0
        if options.native_library is None:
            parser.error("--native-library is required for native qualification")
        result = run_qualification(options.corpus, options.output, native_library=options.native_library,
                                  selected_cases=tuple(options.case), split=options.split, quick=options.quick)
    except (ImportError, OSError, ValueError) as exc:
        print(f"Native qualification unavailable: {exc}", file=sys.stderr)
        return 2
    print(f"D3 analytic native subset: {result['qualification_status']}; complete matrix: {result['complete_matrix']}")
    print(f"Report: {options.output.resolve() / 'qualification.json'}")
    print("D4-D8 remain UNKNOWN; initial D7 tranche and #84 remain open.")
    return 0 if result["qualification_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
