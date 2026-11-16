"""Offline D7 evidence replay. No generation request, credential or paid call."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "lib"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/diagnostic-evidence")
    parser.add_argument("--native-library", type=Path, default=os.environ.get("MESHVENN_TEST_NATIVE_LIBRARY"))
    parser.add_argument("--corpus", action="append", choices=("D2", "D3", "D4", "D5", "D6"))
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--archive", type=Path, help="Verify an existing immutable host-tool archive.")
    inputs.add_argument("--attempt", type=Path, help="Import an already observed local attempt manifest; never invokes its tool.")
    parser.add_argument("--reference", type=Path, default=ROOT / "tests/fixtures/diagnostics/provider-v1")
    parser.add_argument("--review", type=Path, help="Import a person's JSON separately from the immutable image archive.")
    parser.add_argument("--verify-only", action="store_true", help="Verify bytes and compare archived pixels without rerunning diagnostic corpora.")
    parser.add_argument("--require-complete-regressions", action="store_true")
    parser.add_argument("--require-qualified-delivery", action="store_true", help="Fail on any required failure or unknown, including missing D8 evidence.")
    options = parser.parse_args(argv)
    from scripts.diagnostic_qualification.runner import run_evidence
    try:
        result = run_evidence(options.output, native_library=options.native_library,
                              selection=tuple(options.corpus) if options.corpus else None,
                              archive=options.archive, attempt=options.attempt, reference=options.reference,
                              review=options.review, verify_only=options.verify_only)
    except (ImportError, OSError, ValueError) as exc:
        print("Evidence replay unavailable: " + str(exc), file=sys.stderr)
        return 2
    report = result["report"]
    print("Evidence command: " + report["technical_status"])
    print("Frozen regression replay: " + report["corpora"].get("status", "unknown"))
    print("Delivery qualification: " + report["qualification_status"] + " (required unknowns are not success)")
    print("Report: " + str(result["run_path"] / "report.json"))
    print("Offline review: " + str(result["run_path"] / "review.html"))
    print("No live provider request was dispatched. Real-provider and human/D8 qualification remain scoped to recorded evidence.")
    if report["technical_status"] != "completed":
        return 1
    if options.require_complete_regressions and not report["corpora"].get("all_full_matrices_passed", False):
        return 1
    if options.require_qualified_delivery and report["qualification_status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
