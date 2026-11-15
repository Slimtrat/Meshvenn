"""Evaluate the real D6 machine/store with scoped local ports and actual evidence."""
from __future__ import annotations

import importlib
from pathlib import Path
import platform
import sys
from time import perf_counter

from scripts.appearance_diagnostic_corpus.authoring import canonical_json,sha256
from .harness import execute_case
from .integrity import load_manifest
from .scoring import score_case


def implementation_provenance():
    runtime=importlib.import_module("meshvenn_engine.loop_runtime")
    model=importlib.import_module("meshvenn_engine.core.correction_loop.models")
    core=Path(model.__file__).parents[1]
    library=Path(runtime.__file__).parent
    repo=Path(__file__).resolve().parents[2]
    sources={}
    for folder in ("correction_loop","correction_plans","diagnostic_contracts","diagnostics_preflight",
                   "appearance_diagnostics","geometry_diagnostics","material_visibility","projection_math"):
        for path in sorted((core/folder).rglob("*.py")):
            sources["core/"+path.relative_to(core).as_posix()]=sha256(path.read_bytes())
    for name in ("image_mask.py","projection_alignment.py","projection_frame.py"):
        sources["core/"+name]=sha256((core/name).read_bytes())
    for name in ("loop_runtime.py","loop_runtime_ops.py","loop_store.py","errors.py"):
        sources["lib/meshvenn_engine/"+name]=sha256((library/name).read_bytes())
    for folder in ("correction_loop_corpus","correction_plan_corpus","appearance_diagnostic_corpus"):
        for path in sorted((repo/"scripts"/folder).rglob("*.py")):
            sources[path.relative_to(repo).as_posix()]=sha256(path.read_bytes())
    entry=repo/"scripts/qualify_correction_loops.py"
    sources[entry.relative_to(repo).as_posix()]=sha256(entry.read_bytes())
    return {"source_sha256":sources,"python_version":platform.python_version(),
            "python_executable_sha256":sha256(Path(sys.executable).read_bytes()),
            "platform":{"system":platform.system(),"machine":platform.machine()}}


def run_qualification(root,output,*,selected_cases=()):
    started=perf_counter()
    manifest,digest=load_manifest(root)
    unknown=set(selected_cases)-{c["case_id"] for c in manifest["cases"]}
    if unknown:raise ValueError("Unknown loop case: "+", ".join(sorted(unknown)))
    cases=[c for c in manifest["cases"] if not selected_cases or c["case_id"] in selected_cases]
    implementation=implementation_provenance()
    identity=sha256(canonical_json({"manifest":digest,"implementation":implementation}))
    attempt=1
    while True:
        run=output/"runs"/(identity[:16]+"-"+str(attempt))
        try:run.mkdir(parents=True,exist_ok=False);break
        except FileExistsError:attempt+=1
    records=[]
    for case in cases:
        case_started=perf_counter()
        destination=run/case["case_id"]
        destination.mkdir(parents=True,exist_ok=True)
        record={"case_id":case["case_id"],"split":case["split"],"scope":case["scope"],
                "path":destination.relative_to(output).as_posix()}
        try:
            record.update(execute_case(root,case,manifest,destination))
        except Exception as exc:
            record["execution_failure"]={"error_type":type(exc).__name__,"message":str(exc)}
        record["elapsed_seconds"]=perf_counter()-case_started
        record["score"]=score_case(case,record)
        (destination/"observation.json").write_bytes(canonical_json(record))
        records.append(record)
        print(f"{case['case_id']}: {'PASS' if record['score']['passed'] else 'FAIL'} {record['score']['failures']}",flush=True)
    unchanged=implementation==implementation_provenance() and digest==load_manifest(root)[1]
    passed=unchanged and bool(records) and all(r["score"]["passed"] for r in records)
    metrics={"evaluations":len(records),"passed":sum(r["score"]["passed"] for r in records),
        "failed":sum(not r["score"]["passed"] for r in records),"assertions":sum(len(r["score"]["assertions"]) for r in records),
        "failed_assertions":sum(len(r["score"]["failures"]) for r in records),
        "unexpected_execution_failures":sum("execution_failure" in r for r in records)}
    summary={"schema_version":1,"corpus_version":manifest["corpus_version"],"manifest_sha256":digest,
        "qualification_identity":identity,"qualification_status":"pass" if passed else "fail",
        "complete_matrix":not selected_cases,"authorities_unchanged":unchanged,"implementation":implementation,
        "metrics":metrics,"records":records,"elapsed_seconds":perf_counter()-started,
        "real_provider_calls":0,"real_paid_cost":0.,"provider_fidelity_qualified":False,"semantic_quality_qualified":False,
        "qualified_scope":"Finite local orchestration with explicitly simulated ports; one actual D2/D4 recheck remains unqualified/unknown",
        "limits":manifest["limits"],"run_path":run.relative_to(output).as_posix(),"previous_attempts_retained":True}
    raw=canonical_json(summary)
    (run/"qualification.json").write_bytes(raw)
    (output/"qualification.json").write_bytes(raw)
    return summary
