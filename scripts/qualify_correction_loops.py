"""Offline frozen D6 orchestration qualification; never provider/model fidelity."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
if str(ROOT/"lib") not in sys.path:sys.path.append(str(ROOT/"lib"))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus",type=Path,default=ROOT/"tests/fixtures/diagnostics/correction-loop-v1")
    parser.add_argument("--output",type=Path,default=ROOT/"tmp/correction-loop-qualification")
    parser.add_argument("--case",action="append",default=[])
    parser.add_argument("--verify-only",action="store_true")
    options=parser.parse_args(argv)
    try:
        if options.verify_only:
            from scripts.correction_loop_corpus.integrity import load_manifest
            manifest,digest=load_manifest(options.corpus)
            print(f"Verified {len(manifest['cases'])} frozen loop cases, manifest {digest}. No machine/provider execution.")
            return 0
        from scripts.correction_loop_corpus.runner import run_qualification
        summary=run_qualification(options.corpus,options.output,selected_cases=tuple(options.case))
    except (ImportError,OSError,ValueError) as exc:
        print("Loop qualification unavailable: "+str(exc),file=sys.stderr)
        return 2
    print(f"Loop orchestration: {summary['qualification_status']}; full matrix: {summary['complete_matrix']}")
    print(f"Report: {options.output.resolve()/'qualification.json'}")
    print("Real provider/model fidelity and D7/#84 remain unqualified/open; simulated promotion is a contract check only.")
    return 0 if summary["qualification_status"]=="pass" else 1


if __name__=="__main__":
    raise SystemExit(main())
