"""Replay nineteen exact consumer poses; fidelity success is not visual acceptance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.modular_character.json_io import strict_json_loads
from core.native_pose_capture import REGIONS, validate_matrix_proof
from core.native_pose_probe import NativePoseProbe
from scripts.extract_stytch_pose_series import INDEX_SHA256
from scripts.replay_stytch_doll_pose import main as replay

DEFAULT_RENDERS = ("factory-held", "Walk-meshvenn-walk-02", "Hop-meshvenn-hop-11")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "example/v2/poses/StytchDoll/complete")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render-cases", nargs="*", default=DEFAULT_RENDERS)
    parser.add_argument("--source-sha", default="local-uncommitted")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--run-attempt", default=None)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    dataset, output = args.dataset.resolve(strict=True), args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty series output directory.")
    index_path = dataset / "index.json"
    if hashlib.sha256(index_path.read_bytes()).hexdigest() != INDEX_SHA256:
        raise ValueError("Series index differs from the explicitly qualified capture revision.")
    index = strict_json_loads(index_path.read_text("utf-8"))
    cases = index["cases"]
    if index["case_count"] != 19 or len(cases) != 19 or len({c["id"] for c in cases}) != 19:
        raise ValueError("Series requires nineteen unique captured poses.")
    if not set(args.render_cases) <= {c["id"] for c in cases}:
        raise ValueError("Unknown requested render case.")
    prepared = []
    for case in cases:
        if not isinstance(case["id"], str) or re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case["id"]) is None:
            raise ValueError("Unsafe capture case identifier.")
        paths = []
        for key in ("probe", "matrix_proof"):
            path = (dataset / case[key]).resolve(strict=True)
            if path.parent != dataset or hashlib.sha256(path.read_bytes()).hexdigest() != case[key+"_sha256"]:
                raise ValueError("Unsafe or mismatched captured matrix file.")
            paths.append(path)
        probe = NativePoseProbe.from_dict(strict_json_loads(paths[0].read_text("utf-8")))
        if probe.asset_sha256 != index["asset_sha256"]:
            raise ValueError("Pose series targets a different native asset.")
        validate_matrix_proof(probe, strict_json_loads(paths[1].read_text("utf-8")))
        if (not isinstance(case["hidden_regions"], list)
                or any(not isinstance(r, str) or r not in REGIONS-{"body-core"} for r in case["hidden_regions"])
                or case["hidden_regions"] != sorted(set(case["hidden_regions"]))):
            raise ValueError("Duplicate or unsorted hidden region provenance.")
        prepared.append((case, paths[0]))
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for case, path in prepared:
        case_dir = output / case["id"]
        argv = ["--pose", str(path), "--output", str(case_dir), "--source-sha", args.source_sha]
        if case["hidden_regions"]:
            argv += ["--hidden-regions", *case["hidden_regions"]]
        if case["id"] not in args.render_cases:
            argv.append("--no-render")
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
              "private_captures_published": False,
              "scope": "Actual synchronized native poses. Ancestor chains validated; skin comparison is before external facing/world transforms, retaining asset normalization once. No physical-contact or consumer repair claim."}
    (output / "series.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", "utf-8")
    assert report["passed"]
    print("Nineteen native/raw-GLB/reimport poses PASS; visual acceptance remains unqualified.")


if __name__ == "__main__":
    main()
