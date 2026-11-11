"""Offline diagnostic qualification CLI; no network, credentials, bpy or model API."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "tests/fixtures/diagnostics/v1")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/diagnostic-qualification")
    parser.add_argument("--regenerate", action="store_true", help="Explicitly regenerate the frozen analytic fixture files before evaluation")
    parser.add_argument("--verify-only", action="store_true", help="Verify hashes/provenance only; this does not qualify diagnostics")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--split", choices=("all", "calibration", "heldout"), default="all")
    options = parser.parse_args(argv)
    if options.regenerate:
        from scripts.diagnostic_corpus.fixtures import build_corpus
        build_corpus(options.corpus)
    try:
        from scripts.diagnostic_corpus.runner import load_manifest, run_qualification
        if options.verify_only:
            manifest, digest = load_manifest(options.corpus)
            print(f"Verified {len(manifest['cases'])} cases; manifest {digest}. No diagnostic qualification executed.")
            return 0
        summary = run_qualification(options.corpus, options.output, selected_cases=tuple(options.case), split=options.split)
    except (ImportError, OSError, ValueError) as exc:
        print(f"Qualification could not run: {exc}", file=sys.stderr)
        return 2
    print(f"D1/D2 analytic subset: {summary['qualification_status']}; {summary['metrics']}")
    print(f"Report: {options.output.resolve() / 'qualification.json'}")
    print("D3-D8 and full #84 acceptance remain UNKNOWN/open.")
    return 0 if summary["qualification_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
