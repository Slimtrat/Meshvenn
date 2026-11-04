"""Replay nineteen exact consumer poses; fidelity success is not visual acceptance."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.modular_character.json_io import strict_json_loads
from scripts.native_pose_coverage import summarize_joint_motion
from scripts.report_stytch_pose_coverage import load_capture_cases
from scripts.replay_stytch_doll_pose import main as replay

DEFAULT_RENDERS = ("factory-held", "Walk-meshvenn-walk-02", "Hop-meshvenn-hop-11")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("original", "shoulder-aligned"), default="original")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render-cases", nargs="*", default=DEFAULT_RENDERS)
    parser.add_argument("--review-views", action="store_true")
    parser.add_argument("--source-sha", default="local-uncommitted")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-attempt", default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty series output directory.")
    profile,index,prepared = load_capture_cases(args.profile,args.dataset)
    cases = index["cases"]
    if not set(args.render_cases) <= {c["id"] for c in cases}:
        raise ValueError("Unknown requested render case.")
    coverage = summarize_joint_motion([{"id":case["id"],"probe":probe,"hidden_regions":case["hidden_regions"]}
                                      for case,_,probe in prepared])
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for case, path, _ in prepared:
        case_dir = output / case["id"]
        argv = ["--fixture", str(profile["fixture"]), "--pose", str(path), "--output", str(case_dir), "--source-sha", args.source_sha]
        if case["hidden_regions"]:
            argv += ["--hidden-regions", *case["hidden_regions"]]
        if case["id"] not in args.render_cases:
            argv.append("--no-render")
        elif args.review_views:
            argv.append("--review-views")
        for flag, value in (("--run-id", args.run_id), ("--run-attempt", args.run_attempt)):
            if value is not None:
                argv += [flag, value]
        replay(argv)
        report = strict_json_loads((case_dir / "replay.json").read_text("utf-8"))
        if report["input_pose_sha256"] != case["probe_sha256"] or report["hidden_regions"] != case["hidden_regions"]:
            raise ValueError("Replay input or visibility does not match captured provenance.")
        summaries.append({"id": case["id"], "movement_classification": case["movement_classification"],
                          "context": case["context"], **report})
    report = {"passed": all(c["passed"] for c in summaries), "case_count": len(summaries),
              "asset_sha256": index["asset_sha256"], "consumer_revision": index["source_revision"],
              "source_sha": args.source_sha, "run_id": args.run_id, "run_attempt": args.run_attempt,
              "cases": summaries, "rendered_cases": sorted(args.render_cases), "visual_qualification": False,
              "capture_profile": args.profile, "dataset_sha256": profile["index_sha256"],
              "replay_is_actual_consumer_capture": True,
              "joint_motion_coverage": coverage,
              "private_captures_published": False,
              "scope": "Actual synchronized native poses. Ancestor chains validated; skin comparison is before external facing/world transforms, retaining asset normalization once. No physical-contact or consumer repair claim."}
    (output / "series.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")
    assert report["passed"]
    print("Nineteen native/raw-GLB/reimport poses PASS; visual acceptance remains unqualified.")


if __name__ == "__main__":
    main()
