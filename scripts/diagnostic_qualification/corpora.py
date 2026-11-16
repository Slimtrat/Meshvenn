"""Replay existing frozen corpus CLIs; never invent new quality thresholds."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from time import perf_counter

from .integrity import checked_path,file_record,inventory_tree,read_json,sha256_file,verify_file,verify_inventory

_ROOT=Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CorpusSpec:
    id: str
    script: str
    fixture: str
    records: str = "records"
    timeout_seconds: int = 1800


_SPECS=(CorpusSpec("D2","qualify_diagnostics.py","v1","cases"),
        CorpusSpec("D3","qualify_geometry_diagnostics.py","geometry-v1"),
        CorpusSpec("D4","qualify_appearance_diagnostics.py","appearance-v1"),
        CorpusSpec("D5","qualify_correction_plans.py","correction-plan-v1",timeout_seconds=600),
        CorpusSpec("D6","qualify_correction_loops.py","correction-loop-v1",timeout_seconds=600))


def _aggregation_sources():
    package=Path(__file__).resolve().parent
    return {"scripts/diagnostic_qualification/"+name:sha256_file(package/name)
            for name in ("corpora.py","integrity.py")}


def _json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()


def _invoke(command,stdout,stderr,timeout_seconds):
    started=perf_counter()
    with stdout.open("wb") as out,stderr.open("wb") as err:
        process=subprocess.Popen(command,cwd=_ROOT,stdout=out,stderr=err,start_new_session=os.name!="nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=="nt" else 0)
        timed_out=False
        try:process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out=True
            if os.name=="nt":
                try:subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],timeout=10,
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                except (OSError,subprocess.TimeoutExpired):process.kill()
            else:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=10)
    return {"exit_code":process.returncode,"timed_out":timed_out,"elapsed_seconds":perf_counter()-started}


def _expected_rows(spec,manifest):
    """Validate matrix coverage, not verdicts or algorithm thresholds."""
    expected=set()
    for case in manifest["cases"]:
        cid=case["case_id"]
        if spec.id=="D2":
            expected.update((cid,v["resolution"]) for v in case["variants"])
        elif spec.id=="D3":
            plan=manifest["execution_plan"]
            operational=case["injection"] in ("deadline","native_invalid_resolution")
            configs=plan["configurations"][:1] if operational else plan["configurations"]
            for index,config in enumerate(configs):
                orders=plan["orders"] if index==0 and not operational else ("canonical",)
                expected.update((cid,config["raster"],config["voxel"],order) for order in orders)
        elif spec.id=="D4":
            expected.update((cid,v["raster_resolution"],order) for v in case["variants"] for order in manifest["execution_plan"]["orders"])
        elif spec.id=="D5":
            expected.update((cid,order) for order in manifest["evaluation_plan"]["report_orders"])
        else:expected.add((cid,))
    return expected


def _row_key(spec,row):
    names={"D2":("case_id","resolution"),"D3":("case_id","raster_resolution","voxel_resolution","order"),
           "D4":("case_id","raster_resolution","order"),"D5":("case_id","order"),"D6":("case_id",)}[spec.id]
    return tuple(row[name] for name in names)


def _score(spec,row):
    score=row.get("scoring" if spec.id=="D2" else "score",{})
    if type(score) is not dict:raise ValueError("Malformed measured per-record corpus score")
    passed=score.get("passed_expectations" if spec.id=="D2" else "passed")
    if type(passed) is not bool:raise ValueError("Missing measured per-record corpus score")
    return passed,score


def _record_directory(spec,row,summary):
    if spec.id=="D2":return str(Path(row["report"]).parent).replace("\\","/")
    if spec.id in ("D3","D4","D6"):return row["path"]
    return summary["run_path"]+"/"+row["case_id"]+"/"+row["order"]


def _validate_evidence(spec,summary,rows,root):
    """Explicit output contracts: missing raw archives never become evidence."""
    if spec.id!="D2":
        archived=checked_path(root,summary["run_path"]+"/qualification.json")
        if read_json(archived)!=summary:raise ValueError("Archived summary differs from the runner result")
    findings=[]
    policies=[]
    def policy(value):
        if isinstance(value,dict):policies.append(value)
    for value in summary.get("policies",[]):policy(value)
    for row in rows:
        directory=checked_path(root,_record_directory(spec,row,summary))
        observation=directory/("observations.json" if spec.id=="D2" else "observation.json")
        if read_json(observation)!=row:raise ValueError("Raw observation archive differs from its summary record")
        if spec.id=="D2":
            report=read_json(checked_path(root,row["report"]))
            findings.extend(report["findings"])
        elif spec.id in ("D3","D4"):
            report=read_json(directory/"diagnostic-report.json")
            if report!=row["report"]:raise ValueError("Diagnostic report archive differs from its summary")
            findings.extend(report["findings"])
        elif spec.id=="D5":
            result=read_json(directory/"correction-result.json")
            if result!=row["result"]:raise ValueError("Correction plan archive differs from its summary")
            findings.extend(f for report in row["reports"] for f in report["findings"])
            for prepared in row["prepared"]:
                if read_json(checked_path(directory,prepared["plan_id"]+"-prepared.json"))!=prepared:
                    raise ValueError("Prepared package differs from its archive")
        else:
            state=read_json(directory/"last-state.json")
            history=read_json(directory/"history.json")
            if not history or history[-1]!=state:raise ValueError("Final loop state differs from durable history")
            for name in ("start-payload.json","observed-events.json","provider-receipts.json","evaluations.json"):
                read_json(directory/name)
            for name in ("budget","acceptance_policy","correction_policy"):policy(state.get(name))
            findings.extend(c for evaluation in row["facts"]["evaluations"] for c in evaluation["checks"])
        policy(row.get("policy"))
        for artifact in row.get("evidence",row.get("artifacts",[])):
            checked={key:artifact[key] for key in ("path","sha256")}
            path=checked_path(directory,checked["path"])
            if sha256_file(path)!=checked["sha256"]:raise ValueError("Declared evidence hash does not match")
        if "result_artifact" in row:
            checked=row["result_artifact"]
            if verify_file(directory,checked)["status"]!="pass":raise ValueError("Strict result artifact is missing or changed")
    documents={hashlib.sha256(_json_bytes(p)).hexdigest():p for p in policies}
    if any(type(f) is not dict or type(f.get("code")) is not str or f.get("status") not in
           ("pass","fail","unknown","not_applicable") for f in findings):
        raise ValueError("Malformed retained diagnostic findings")
    hashes=[{"sha256":digest,"document":documents[digest]} for digest in sorted(documents)]
    return findings,hashes


def _summarize(spec,summary,manifest,root):
    if type(summary) is not dict or summary.get("schema_version")!=1:
        raise ValueError("Malformed/unsupported corpus result")
    if summary.get("qualification_status") not in ("pass","fail","unqualified","unknown"):
        raise ValueError("Missing corpus qualification status")
    if type(summary.get("complete_matrix")) is not bool or type(summary.get("implementation")) is not dict:
        raise ValueError("Missing corpus completeness/source provenance")
    rows=summary.get(spec.records)
    if not isinstance(rows,list) or not rows:raise ValueError("Corpus result contains no measured records")
    expected=_expected_rows(spec,manifest)
    observed=[_row_key(spec,row) for row in rows]
    if len(observed)!=len(set(observed)):raise ValueError("Duplicate measured corpus rows")
    if not set(observed)<=expected:raise ValueError("Unexpected corpus case/configuration")
    if summary["complete_matrix"] and set(observed)!=expected:raise ValueError("Claimed complete matrix is missing case/configurations")
    declared={c["case_id"]:c["split"] for c in manifest["cases"]}
    failures=[]
    splits={name:{"original_split":name,"exposure":"regression_exposed","evaluations":0,"passed":0,"failed":0}
            for name in sorted(set(declared.values()))}
    for row in rows:
        if row.get("split")!=declared[row["case_id"]]:raise ValueError("Original corpus split was changed")
        passed,score=_score(spec,row)
        split=splits[row["split"]]
        split["evaluations"]+=1;split["passed" if passed else "failed"]+=1
        if not passed or row.get("error") or row.get("execution_failure"):
            failures.append({"case_id":row["case_id"],"configuration":list(_row_key(spec,row))[1:],
                             "score":score,"execution_failure":row.get("execution_failure",row.get("error"))})
    if summary["qualification_status"]=="pass" and failures:raise ValueError("Passing summary hides failed corpus records")
    findings,policy_hashes=_validate_evidence(spec,summary,rows,root)
    unknown=Counter(f["code"] for f in findings if f.get("status")=="unknown")
    diagnostic_status=Counter(f["status"] for f in findings)
    return {"by_split":splits,"failures":failures,"policy_hashes":policy_hashes,
            "unknowns":{"findings_count":sum(unknown.values()),"by_code":dict(sorted(unknown.items())),
                "diagnostic_status_counts":dict(sorted(diagnostic_status.items())),
                "limits":summary.get("scope_limits",summary.get("limits",summary.get("unevaluated",[]))),
                "unavailable":summary.get("unavailable",[]),
                "semantic_quality_qualified":summary.get("semantic_quality_qualified",False)},
            "coverage_complete":set(observed)==expected}


def run_corpora(output: Path, *, native_library: Path | None=None, selection: tuple[str,...] | None=None) -> dict:
    """Execute frozen full runners, preserving failures and all relative outputs.

    ``status`` describes corpus regression controls only. This function never
    grants asset certification, provider fidelity or human acceptance.
    """
    started=perf_counter()
    aggregation_sources=_aggregation_sources()
    known={spec.id for spec in _SPECS}
    requested=known if selection is None else set(selection)
    if not requested or not requested<=known or selection is not None and len(selection)!=len(requested):
        raise ValueError("Select unique known corpora D2, D3, D4, D5, D6")
    output=Path(output).absolute();output.mkdir(parents=True,exist_ok=True)
    number=1
    while True:
        run=output/"corpora"/f"{number:04d}"
        try:run.mkdir(parents=True,exist_ok=False);break
        except FileExistsError:number+=1
    results=[]
    native=Path(native_library).absolute() if native_library is not None else None
    native_available=native is not None and native.is_file()
    for spec in _SPECS:
        if spec.id not in requested:continue
        begin=perf_counter();root=run/spec.id;root.mkdir()
        relative=lambda path:path.relative_to(output).as_posix() if path is not None else None
        entry={"id":spec.id,"status":"unknown","technical_status":"unavailable","runner_status":None,
            "complete_matrix":None,"corpus_version":"unknown","scope":None,
            "outputs":{"root":relative(root),"summary":None,"inventory":None,"stdout":None,"stderr":None},
            "sources":{"manifest":{},"implementation":{},"policy_hashes":[]},
            "metrics":{},"by_split":{},"unknowns":{},"failures":[],"issues":[]}
        def issue(code,message):entry["issues"].append({"code":code,"message":str(message)[:2048]})
        try:
            manifest_path=_ROOT/"tests/fixtures/diagnostics"/spec.fixture/"manifest.json"
            manifest=read_json(manifest_path)
            if type(manifest) is not dict or not isinstance(manifest.get("cases"),list) or not manifest["cases"]:
                raise ValueError("Malformed corpus input manifest")
            manifest_record=file_record(manifest_path,_ROOT)
            entry["sources"]["manifest"]=manifest_record
            entry["sources"]["runner_script"]=file_record(_ROOT/"scripts"/spec.script,_ROOT)
            entry["corpus_version"]=str(manifest.get("corpus_version","unknown"))
            (root/"input-manifest.json").write_bytes(manifest_path.read_bytes())
            if spec.id=="D3" and not native_available:
                issue("native_unavailable","D3 was not evaluated: configure an explicit readable native library")
            else:
                stdout,stderr=root/"stdout.log",root/"stderr.log"
                entry["outputs"].update(stdout=relative(stdout),stderr=relative(stderr))
                command=[sys.executable,"-I",str(_ROOT/"scripts"/spec.script),"--corpus",str(manifest_path.parent),"--output",str(root)]
                if spec.id in ("D3","D5") and native_available:command.extend(("--native-library",str(native)))
                entry["command"]=command
                execution=_invoke(command,stdout,stderr,spec.timeout_seconds)
                entry["execution"]=execution
                entry["technical_status"]="timed_out" if execution["timed_out"] else "completed"
                report_path=root/"qualification.json"
                if report_path.is_file():
                    entry["outputs"]["summary"]=relative(report_path)
                    entry["summary_sha256"]=sha256_file(report_path)
                    summary=read_json(report_path)
                    if type(summary) is not dict:raise ValueError("Corpus result must be a JSON object")
                    entry["runner_status"]=summary.get("qualification_status")
                    entry["runner_qualification_identity"]=summary.get("qualification_identity")
                    entry["complete_matrix"]=summary.get("complete_matrix")
                    entry["scope"]=summary.get("qualified_scope",summary.get("scope"))
                    entry["metrics"]=summary.get("metrics",{})
                    entry["sources"]["implementation"]=summary.get("implementation",{})
                    if summary.get("manifest_sha256")!=manifest_record["sha256"]:raise ValueError("Runner manifest does not match the frozen input")
                    extracted=_summarize(spec,summary,manifest,root)
                    entry.update({k:extracted[k] for k in ("by_split","unknowns","failures")})
                    entry["sources"]["policy_hashes"]=extracted["policy_hashes"]
                    stable=summary.get("authorities_unchanged",summary.get("implementation_sources_unchanged_during_run"))
                    if stable is not True:issue("source_authorities_changed","Runner source authorities were not stable")
                    if not summary["complete_matrix"] or not extracted["coverage_complete"]:
                        issue("matrix_incomplete","Full native/corpus matrix was not established; partial results stay unqualified")
                    exit_expected=execution["exit_code"]==0 if entry["runner_status"]=="pass" else execution["exit_code"]==1 if entry["runner_status"]=="fail" else True
                    if not exit_expected:issue("exit_status_mismatch","Process exit does not support its reported qualification status")
                    if execution["timed_out"]:issue("runner_timed_out","Runner exceeded its bounded execution time")
                    if not entry["issues"]:
                        entry["status"]=entry["runner_status"] if entry["runner_status"] in ("pass","fail") else "unknown"
                    if not exit_expected:entry["technical_status"]="failed"
                else:
                    entry["technical_status"]="timed_out" if execution["timed_out"] else "failed"
                    issue("missing_qualification","Runner produced no machine-readable qualification archive")
            if sha256_file(manifest_path)!=manifest_record["sha256"]:raise ValueError("Frozen manifest changed during execution")
        except (OSError,ValueError,KeyError,TypeError) as exc:
            entry["technical_status"]="failed";entry["status"]="unknown"
            issue("unverifiable_corpus_result",exc)
        try:
            inventory=inventory_tree(root)
            verification=verify_inventory(root,inventory)
            if verification["status"]!="pass":raise ValueError("Evidence inventory verification failed")
            path=run/(spec.id+".inventory.json");path.write_bytes(_json_bytes(inventory))
            entry["outputs"]["inventory"]=relative(path)
            entry["inventory_sha256"]=sha256_file(path)
        except (OSError,ValueError) as exc:
            entry["technical_status"]="failed";entry["status"]="unknown";issue("evidence_integrity_failed",exc)
        entry["elapsed_seconds"]=perf_counter()-begin
        results.append(entry)
    stable=aggregation_sources==_aggregation_sources()
    selected_pass=stable and bool(results) and all(r["status"]=="pass" and r["complete_matrix"] is True for r in results)
    status="fail" if any(r["status"]=="fail" for r in results) else "pass" if selected_pass else "unknown"
    return {"schema_version":1,"kind":"frozen_corpora_replay","status":status,"verification_status":"unknown",
            "selection":[r["id"] for r in results],"all_full_matrices_passed":selected_pass and requested==known,
            "selected_full_matrices_passed":selected_pass,"regression_exposed":True,
            "aggregation_sources":aggregation_sources,"aggregation_sources_unchanged":stable,
            "elapsed_seconds":perf_counter()-started,"results":results}
