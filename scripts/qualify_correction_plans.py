"""Offline qualification of frozen D5 planning and checked request packages."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus",type=Path,default=ROOT/"tests/fixtures/diagnostics/correction-plan-v1")
    parser.add_argument("--output",type=Path,default=ROOT/"tmp/correction-plan-qualification")
    parser.add_argument("--native-library",type=Path,help="Explicit real library for two native D3 controls; never inferred from a worktree")
    parser.add_argument("--python-executable",type=Path,default=Path(sys.executable))
    parser.add_argument("--case",action="append",default=[])
    parser.add_argument("--verify-only",action="store_true")
    options = parser.parse_args(argv)
    try:
        if options.verify_only:
            from scripts.correction_plan_corpus.integrity import load_manifest
            manifest,digest = load_manifest(options.corpus)
            print(f"Verified {len(manifest['cases'])} frozen correction cases, manifest {digest}. No D5 evaluation executed.")
            return 0
        from scripts.correction_plan_corpus.runner import run_qualification
        summary = run_qualification(options.corpus,options.output,native_library=options.native_library,
            python_executable=options.python_executable,selected_cases=tuple(options.case))
    except (ImportError,OSError,ValueError) as exc:
        print("Correction qualification unavailable: "+str(exc),file=sys.stderr)
        return 2
    print(f"Correction planning: {summary['qualification_status']}; complete matrix: {summary['complete_matrix']}")
    print(f"Report: {options.output.resolve()/'qualification.json'}")
    print("No provider was executed or qualified. Semantic identity, D6-D8, initial D7 and #84 remain UNKNOWN/open.")
    return 0 if summary["qualification_status"]=="pass" else 2 if summary["unavailable"] else 1


if __name__=="__main__":
    raise SystemExit(main())
