"""Offline D4 appearance qualification on frozen original analytic evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus",type=Path,default=ROOT/"tests/fixtures/diagnostics/appearance-v1")
    parser.add_argument("--output",type=Path,default=ROOT/"tmp/appearance-qualification")
    parser.add_argument("--case",action="append",default=[])
    parser.add_argument("--split",choices=("all","calibration","heldout"),default="all")
    parser.add_argument("--quick",action="store_true",help="Baseline raster/canonical order only; no full qualification claim")
    parser.add_argument("--verify-only",action="store_true",help="Integrity checks only; no appearance quality evaluation")
    parser.add_argument("--regenerate",action="store_true",help="Explicitly recreate fixtures from the frozen independent authoring recipe")
    options = parser.parse_args(argv)
    try:
        if options.regenerate:
            from scripts.appearance_diagnostic_corpus.fixtures import build_corpus
            build_corpus(options.corpus)
        if options.verify_only:
            from scripts.appearance_diagnostic_corpus.integrity import load_manifest
            manifest,digest = load_manifest(options.corpus)
            print(f"Verified {len(manifest['cases'])} frozen authored cases, manifest {digest}. No D4 quality evaluation executed.")
            return 0
        from scripts.appearance_diagnostic_corpus.runner import run_qualification
        summary = run_qualification(options.corpus,options.output,selected_cases=tuple(options.case),split=options.split,quick=options.quick)
    except (ImportError,OSError,ValueError) as exc:
        print(f"Appearance qualification unavailable: {exc}",file=sys.stderr)
        return 2
    print(f"Analytic appearance subset: {summary['qualification_status']}; complete matrix: {summary['complete_matrix']}")
    print(f"Report: {options.output.resolve()/'qualification.json'}")
    print("Semantic service mocks qualify adapters only. General semantic identity, D5-D8 and full #84 remain UNKNOWN/open.")
    return 0 if summary["qualification_status"]=="pass" else 1


if __name__=="__main__":
    raise SystemExit(main())
