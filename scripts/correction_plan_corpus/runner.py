"""Evaluate real upstream diagnostics and the actual pure D5 planner offline."""
from __future__ import annotations

from dataclasses import asdict, fields, is_dataclass, replace
from enum import Enum
import importlib
from pathlib import Path
import platform
import sys
from time import perf_counter

from core.diagnostic_contracts import Region
from scripts.appearance_diagnostic_corpus.authoring import canonical_json, sha256
from .integrity import load_manifest
from .scoring import score_case, signature
from .sources import NativeLibraryRequired, execute_source, source_snapshot


def jsonable(value):
    if isinstance(value,Enum):
        return value.value
    if is_dataclass(value):
        return {f.name:jsonable(getattr(value,f.name)) for f in fields(value)}
    if isinstance(value,(tuple,list)):
        return [jsonable(item) for item in value]
    if isinstance(value,dict):
        return {str(k):jsonable(v) for k,v in value.items()}
    return value


def implementation_provenance(native_library=None):
    prefixes = ("core.correction_plans","core.diagnostic_contracts","core.diagnostics_preflight",
                "core.appearance_diagnostics","core.geometry_diagnostics","core.projection_math",
                "core.native_bridge","core.material_visibility","scripts.correction_plan_corpus","scripts.appearance_diagnostic_corpus",
                "scripts.geometry_diagnostic_corpus")
    sources = {}
    for prefix in prefixes:
        module = importlib.import_module(prefix)
        path = Path(module.__file__)
        paths = path.parent.rglob("*.py") if path.name=="__init__.py" else (path,)
        for source in sorted(paths):
            name = prefix+"."+".".join(source.relative_to(path.parent).with_suffix("").parts) if source!=path else prefix
            sources[name] = sha256(source.read_bytes())
    for name in ("core.native_loader","core.image_mask","core.projection_frame","core.projection_alignment"):
        sources[name] = sha256(Path(importlib.import_module(name).__file__).read_bytes())
    sources["scripts.qualify_correction_plans"] = sha256((Path(__file__).parents[1]/"qualify_correction_plans.py").read_bytes())
    return {"source_sha256":sources,"python_version":platform.python_version(),
            "python_executable_sha256":sha256(Path(sys.executable).read_bytes()),
            "native_library_sha256":sha256(Path(native_library).read_bytes()) if native_library else None,
            "platform":{"system":platform.system(),"machine":platform.machine()}}


def capabilities_for(case):
    from core.correction_plans import ProviderCapabilities
    c = case["capabilities"]
    controls = ["identity_reference","multiple_references"]
    controls += [name for field,name in (("image_edit","region_edit"),("masks","mask"),("camera_constraints","camera_request")) if c[field]]
    return ProviderCapabilities(c["profile_id"],c["version"],tuple(controls),c["max_references"])


def annotations_for(context):
    from core.correction_plans import EditAnnotation
    source = context["annotation"]
    if source is None:
        return ()
    region = source["region"]
    candidates = []
    for report in context["reports"]:
        for finding in report.findings:
            if finding.code!="appearance.color_consistency" or finding.status!="fail":
                continue
            for measured in finding.regions:
                if measured.view_id==region.view_id and measured.bounds:
                    l,b,r,t = measured.bounds
                    al,ab,ar,at = region.bounds
                    if l<=al<ar<=r and b<=ab<at<=t:
                        candidates.append(((r-l)*(t-b),finding.finding_id,report,finding))
    if not candidates:
        return ()
    _,_,report,finding = min(candidates,key=lambda item:(item[0],item[1]))
    return (EditAnnotation(sha256(report.to_json().encode()),finding.finding_id,region,
                           source["provenance"],source["mask"]),)


def dependency_bindings(result, view_set, reports, capabilities, annotations, policy):
    hashes = {sha256(r.to_json().encode()):r for r in reports}
    if result.view_set.dependency_fingerprint!=view_set.dependency_fingerprint or result.capabilities!=capabilities or \
            result.policy_sha256!=policy.dependency_fingerprint or getattr(result,"policy",None)!=policy or \
            result.annotations!=annotations or {sha256(r.to_json().encode()) for r in result.reports}!=set(hashes):
        return False
    for plan in result.plans:
        if plan.context_sha256!=result.context_sha256:
            return False
        for evidence in plan.evidence:
            report = hashes.get(evidence.report_sha256)
            finding = next((f for f in report.findings if f.finding_id==evidence.finding_id),None) if report else None
            if finding is None or evidence.code!=finding.code or evidence.status!=finding.status or evidence.observations!=finding.evidence:
                return False
    return True


def check_stale(case, plan, view_set, reports, capabilities, annotations, policy):
    from core.correction_plans import prepare_correction
    mutation = case["prepare_mutation"]
    if mutation is None:
        return None
    kind = mutation["kind"]
    if kind=="source":
        views = tuple(replace(v,revision=v.revision+1,image=replace(v.image,sha256=sha256(b"new original source revision")))
                      if v.view_id=="target" else v for v in view_set.views)
        view_set = replace(view_set,revision=view_set.revision+1,views=views)
    elif kind=="capabilities":
        capabilities = replace(capabilities,version="2")
    elif kind=="report":
        selected = next((i for i,r in enumerate(reports) if any(f.finding_id==plan.evidence[0].finding_id for f in r.findings)),0)
        report = reports[selected]
        finding = report.findings[0]
        changed = replace(finding,message=finding.message+" [new diagnostic snapshot]")
        reports = tuple(replace(r,findings=(changed,)+r.findings[1:]) if i==selected else r for i,r in enumerate(reports))
    elif kind=="policy":
        policy = replace(policy,min_region_pixels=policy.min_region_pixels+1)
    outcome = {"kind":kind,"mutation_constructed":True,"prepare_called":True,"rejected":False}
    try:
        prepare_correction(plan,view_set,reports,capabilities=capabilities,annotations=annotations,policy=policy)
    except ValueError as exc:
        outcome.update(rejected=True,error_type=type(exc).__name__,message=str(exc))
    return outcome


def upstream_record(context):
    result = context["upstream_result"]
    value = {"kind":context["upstream_kind"],"semantic_mock_calls":context["semantic_mock_calls"],
             "alignment_proposals":len(getattr(result,"proposals",())),
             "native_library_sha256":context.get("native_library_sha256"),
             "native_library_name":context.get("native_library_name")}
    if hasattr(result,"identity_status"):
        value.update(identity_status=result.identity_status,
                     views=[{"view_id":v.view_id,"regions":jsonable(v.regions)} for v in result.views],
                     semantic_claims=jsonable(result.semantic.claims) if result.semantic else [])
    if hasattr(result,"provenance"):
        value["provenance"] = jsonable(result.provenance)
    return value


def save_sources(destination, context):
    destination.mkdir(parents=True,exist_ok=True)
    result = context["upstream_result"]
    if hasattr(result,"to_json"):
        (destination/"upstream-result.json").write_text(result.to_json(),encoding="utf-8",newline="\n")
    for index,report in enumerate(context["reports"]):
        (destination/f"upstream-report-{index}.json").write_text(report.to_json(),encoding="utf-8",newline="\n")
    for view,assets in context["asset_paths"].items():
        for role,path in assets.items():
            (destination/f"original-{view}-{role}.png").write_bytes(path.read_bytes())
    if context.get("original_authoring_path"):
        (destination/"original-authoring-source.json").write_bytes(context["original_authoring_path"].read_bytes())
    if context["upstream_kind"]=="actual_D4":
        from scripts.appearance_diagnostic_corpus.evidence import write_evidence
        write_evidence(destination,result)


def run_qualification(root, output, *, native_library=None, python_executable=None, selected_cases=()):
    from core.correction_plans import CorrectionPolicy, CorrectionResult, PreparedCorrection, plan_corrections, prepare_correction
    started = perf_counter()
    manifest,digest = load_manifest(root)
    unknown = set(selected_cases)-{c["case_id"] for c in manifest["cases"]}
    if unknown:
        raise ValueError("Unknown correction cases: "+", ".join(sorted(unknown)))
    cases = [c for c in manifest["cases"] if not selected_cases or c["case_id"] in selected_cases]
    implementation = implementation_provenance(native_library)
    policy = CorrectionPolicy()
    identity = sha256(canonical_json({"manifest":digest,"implementation":implementation,"policy":asdict(policy)}))
    index = 1
    while True:
        run = output/"runs"/(identity[:16]+"-"+str(index))
        try:
            run.mkdir(parents=True,exist_ok=False)
            break
        except FileExistsError:
            index += 1
    records,orders,unavailable = [],[],[]
    for case in cases:
        source_started = perf_counter()
        destination = run/case["case_id"]
        try:
            context = execute_source(root,case,native_library=native_library,python_executable=python_executable)
            save_sources(destination/"sources",context)
        except NativeLibraryRequired as exc:
            unavailable.append({"case_id":case["case_id"],"reason":str(exc)})
            print(case["case_id"]+": UNQUALIFIED (explicit native library required)",flush=True)
            continue
        except Exception as exc:
            for order in manifest["evaluation_plan"]["report_orders"]:
                target = destination/order
                target.mkdir(parents=True,exist_ok=True)
                record = {"case_id":case["case_id"],"split":case["split"],"order":order,
                          "execution_failure":{"phase":"upstream","error_type":type(exc).__name__,"message":str(exc)}}
                record["score"] = score_case(case,record)
                (target/"observation.json").write_bytes(canonical_json(record))
                records.append(record)
            orders.append({"case_id":case["case_id"],"report_orders":0,"passed":False,"context_fingerprints":[]})
            print(case["case_id"]+": FAIL actual upstream execution: "+str(exc),flush=True)
            continue
        source_elapsed = perf_counter()-source_started
        annotations = annotations_for(context)
        capabilities = capabilities_for(case)
        case_records = []
        for order in manifest["evaluation_plan"]["report_orders"]:
            call_started = perf_counter()
            view_set = context["view_set"]
            reports = context["reports"]
            if order=="reverse":
                view_set = replace(view_set,input_order=tuple(reversed(view_set.input_order)))
                reports = tuple(reversed(reports))
            before = source_snapshot(view_set,context["inputs"])
            record = {"case_id":case["case_id"],"split":case["split"],"order":order,
                      "upstream":upstream_record(context),"upstream_elapsed_seconds":source_elapsed,
                      "reports":[r.to_dict() for r in reports],"policy":asdict(policy),
                      "provider_execution_calls":0,"provider_fidelity_qualified":False,
                      "accepted_reference_ids":list(view_set.canonical_reference.view_ids) if view_set.canonical_reference else [],
                      "target_original_sha256":next((v.image.sha256 for v in view_set.views if v.view_id=="target"),None),
                      "prepare_mutation":None,"prepared":[]}
            target = destination/order
            target.mkdir(parents=True,exist_ok=True)
            try:
                result = plan_corrections(view_set,reports,capabilities=capabilities,annotations=annotations,policy=policy)
                raw = result.to_json()
                (target/"correction-result.json").write_text(raw,encoding="utf-8",newline="\n")
                record.update(result=result.to_dict(),contract_roundtrip_passed=CorrectionResult.from_json(raw).to_json()==raw,
                              dependency_bindings_passed=dependency_bindings(result,view_set,reports,capabilities,annotations,policy))
                for plan in result.plans:
                    if plan.action_kind=="edit_region" and plan.readiness=="ready":
                        prepared = prepare_correction(plan,view_set,reports,capabilities=capabilities,annotations=annotations,policy=policy)
                        package = prepared.to_json()
                        if PreparedCorrection.from_json(package).to_json()!=package:
                            raise ValueError("Prepared correction strict roundtrip failed")
                        record["prepared"].append(prepared.to_dict())
                        (target/(plan.plan_id+"-prepared.json")).write_text(package,encoding="utf-8",newline="\n")
                if case["prepare_mutation"]:
                    chosen = next((p for p in result.plans if p.action_kind=="edit_region" and p.readiness=="ready"),None)
                    if chosen:
                        record["prepare_mutation"] = check_stale(case,chosen,view_set,reports,capabilities,annotations,policy)
            except Exception as exc:
                record["execution_failure"] = {"error_type":type(exc).__name__,"message":str(exc)}
            record["source_unchanged"] = before==source_snapshot(view_set,context["inputs"])
            record["elapsed_seconds"] = perf_counter()-call_started
            record["score"] = score_case(case,record)
            (target/"observation.json").write_bytes(canonical_json(record))
            records.append(record)
            case_records.append(record)
            print(f"{case['case_id']} {order}: {'PASS' if record['score']['passed'] else 'FAIL'} {record['score']['failures']}",flush=True)
        baseline = case_records[0]
        orders.append({"case_id":case["case_id"],"report_orders":len(case_records),
            "passed":all(r.get("result") and not r.get("execution_failure") for r in case_records) and
                len({r.get("result",{}).get("context_sha256") for r in case_records})==1 and
                all(signature(baseline.get("result",{}))==signature(r.get("result",{})) for r in case_records[1:]),
            "context_fingerprints":[r.get("result",{}).get("context_sha256") for r in case_records]})
    unchanged = implementation==implementation_provenance(native_library) and digest==load_manifest(root)[1]
    passed = bool(records) and unchanged and not unavailable and all(r["score"]["passed"] for r in records) and all(c["passed"] for c in orders)
    summary = {"schema_version":1,"manifest_sha256":digest,"qualification_identity":identity,"implementation":implementation,
        "qualification_status":"pass" if passed else "unqualified" if unavailable else "fail", "authorities_unchanged":unchanged,
        "complete_matrix":not selected_cases and not unavailable,"records":records,"order_checks":orders,"unavailable":unavailable,
        "elapsed_seconds":perf_counter()-started,"provider_execution_calls":0,"provider_fidelity_qualified":False,
        "limits":manifest["limits"],"run_path":run.relative_to(output).as_posix(),"previous_attempts_retained":True}
    summary["metrics"] = {"evaluations":len(records),"passed":sum(r["score"]["passed"] for r in records),
        "failed":sum(not r["score"]["passed"] for r in records),"assertions":sum(len(r["score"]["assertions"]) for r in records),
        "failed_assertions":sum(len(r["score"]["failures"]) for r in records),"execution_failures":sum("execution_failure" in r for r in records)}
    summary["diagnostic_execution_note"] = "Each case executes actual upstream diagnostics once; both planning/report-order invocations use that exact immutable measured snapshot. No upstream quality result is fabricated."
    data = canonical_json(summary)
    (run/"qualification.json").write_bytes(data)
    (output/"qualification.json").write_bytes(data)
    return summary
