"""Run the actual D4 engine on frozen authored sources, offline and bounded."""
from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from enum import Enum
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from core.diagnostic_contracts import (ArtifactReference, CameraDeclaration, CanonicalReference, ContentReference,
    DiagnosticPolicy, DiagnosticReport, DiagnosticResolution, EngineVersion, Evidence, Finding, Region,
    ViewRevision, ViewSetRevision)
from core.diagnostics_preflight import RasterInput, ViewInput

from . import CORPUS_VERSION, SCHEMA_VERSION
from .adapter_mocks import SemanticAdapterFixture
from .authoring import canonical_json, sha256
from .evidence import localization_metrics, mask_bounds, raw_metrics, write_evidence
from .fixtures import REGIONS, projected_bounds
from .integrity import checked_path, load_manifest
from .scoring import score_case, semantic_signature


def jsonable(value):
    if isinstance(value,Enum):
        return value.value
    if isinstance(value,bytes):
        return {"sha256":sha256(value),"byte_count":len(value)}
    if is_dataclass(value):
        if type(value).__name__=="MaskArtifact":
            return {field.name:jsonable(getattr(value,field.name)) for field in fields(value) if field.name!="values_hex"} | {"byte_count":len(value.values)}
        if type(value).__name__=="SemanticImageSnapshot":
            return {field.name:jsonable(getattr(value,field.name)) for field in fields(value) if field.name!="rgba"} | {"rgba_channels":len(value.rgba)}
        return {field.name:jsonable(getattr(value,field.name)) for field in fields(value)}
    if isinstance(value,dict):
        return {str(key):jsonable(item) for key,item in value.items()}
    if isinstance(value,(tuple,list)):
        return [jsonable(item) for item in value]
    return value


def implementation_provenance():
    prefixes = ("core.appearance_diagnostics","core.diagnostic_contracts","core.diagnostics_preflight",
                "core.projection_math","scripts.appearance_diagnostic_corpus")
    authorities = {"core.image_mask","core.projection_alignment","core.projection_frame"}
    sources = {}
    for name,module in sorted(sys.modules.copy().items()):
        if name in authorities or any(name==prefix or name.startswith(prefix+".") for prefix in prefixes):
            filename = getattr(module,"__file__",None)
            if filename and Path(filename).suffix==".py":
                sources[name] = sha256(Path(filename).read_bytes())
    for prefix in prefixes:
        filename = getattr(sys.modules.get(prefix),"__file__",None)
        if not filename or Path(filename).name!="__init__.py":
            continue
        directory = Path(filename).parent
        for path in directory.rglob("*.py"):
            suffix = ".".join(path.relative_to(directory).with_suffix("").parts)
            module_name = prefix if suffix=="__init__" else prefix+"."+suffix.removesuffix(".__init__")
            sources[module_name] = sha256(path.read_bytes())
    sources["scripts.qualify_appearance_diagnostics"] = sha256((Path(__file__).parents[1]/"qualify_appearance_diagnostics.py").read_bytes())
    return {"source_sha256":sources,"python_version":platform.python_version(),
            "python_implementation":platform.python_implementation(),"python_executable_sha256":sha256(Path(sys.executable).read_bytes()),
            "platform":{"system":platform.system(),"machine":platform.machine()},"native_execution":"not required by authored-surface D4 evaluation"}


def inputs_for_case(root, case, variant, order):
    from core.appearance_diagnostics import AppearanceRegionAnchor, AppearanceViewSettings, SurfaceMesh
    proof = ArtifactReference("analytic-authoring-proof",case["source"]["sha256"],"application/json","analytic-source.json")
    views,inputs,settings = [],{},{}
    for role,record in variant["views"].items():
        camera = record["camera"]
        declaration = CameraDeclaration("orthographic",camera["azimuth_degrees"],camera["elevation_degrees"],camera["flip_x"],
                                        camera["verified"],proof if camera["verified"] else None)
        content = ContentReference(record["declared_content_sha256"],record["width"],record["height"],"image/png")
        lineage = record["lineage"]
        views.append(ViewRevision(role,1,content,None,declaration,role="reference" if role=="reference" else "observation",
            origin=lineage["origin"],derived_from=tuple(lineage["derived_from"]),
            origin_details="Original analytic surface fixture; mathematical authorship, not human-reviewed generated imagery."))
        inputs[role] = ViewInput(RasterInput.from_path(checked_path(root,record["path"])))
        settings[role] = AppearanceViewSettings.from_dict(record["appearance_settings"])
    by_id = {view.view_id:view for view in views}
    canonical = CanonicalReference("authored-accepted-design",1,by_id["reference"].image,True,("reference",),proof)
    ids = [view.view_id for view in views]
    if order=="reverse":
        ids.reverse()
    elif order=="rotate":
        ids = ids[1:]+ids[:1]
    elif order!="canonical":
        raise ValueError("Unsupported appearance input permutation")
    view_set = ViewSetRevision("appearance-"+case["case_id"]+"-"+str(variant["raster_resolution"]),1,
                               tuple(by_id[name] for name in ids),canonical,tuple(ids))
    data = json.loads(checked_path(root,case["mesh"]["path"]).read_bytes())
    surface = SurfaceMesh(tuple(tuple(v) for v in data["vertices"]),tuple(tuple(t) for t in data["triangles"]),
        ArtifactReference("authored-triangle-surface",case["mesh"]["sha256"],"application/json","authored-mesh.json"))
    regions,anchors = [],[]
    # A canonical visible region can become hidden in its target. A region
    # invisible in the canonical is instead anchored in the target; an
    # occluder's foreground pixels must not validate the hidden body patch.
    anchor = "target" if case["case_id"]=="occluded_in_reference" else "reference"
    region = Region(anchor,case["expected"]["region_label"],tuple(variant["views"][anchor]["region_projected_bounds"]))
    regions.append(region)
    bounds = case["surface_region"]
    triangles = tuple(i for i,label in enumerate(data["triangle_labels"]) if label==bounds["surface_label"])
    anchors.append(AppearanceRegionAnchor(region,(bounds["x"][0],bounds["y"],bounds["z"][0]),
        (bounds["x"][1],bounds["y"],bounds["z"][1]),proof,triangles))
    if "unaffected_shared_region_numeric_pass" in case["expected"]["required_controls"]:
        bounds = projected_bounds(REGIONS["shared_patch"],variant["views"]["reference"]["camera"]["azimuth_degrees"])
        region = Region("reference","unaffected_shared_region",tuple(bounds))
        regions.append(region)
        shared = REGIONS["shared_patch"]
        anchors.append(AppearanceRegionAnchor(region,(shared["x"][0],shared["y"],shared["z"][0]),
            (shared["x"][1],shared["y"],shared["z"][1]),proof,(0,1)))
    upstream = ()
    if case["upstream"] is not None:
        evidence = Evidence("declared-upstream-state","execution",
            "Declared upstream geometry failure contract specimen; no native D3 quality evaluation was executed.",
            ("reference","target"),artifact=proof)
        finding = Finding("upstream-geometry-failure","geometry.cross_view_conflict","geometry","error","fail",
            "Declared upstream failure must survive D4 composition.",("reference","target"),evidence=(evidence,))
        policy = DiagnosticPolicy("corpus.upstream-state-specimen","1",sha256(canonical_json(case["upstream"])),(finding.code,))
        upstream = (DiagnosticReport("upstream-contract-specimen",view_set,(EngineVersion("corpus.upstream_geometry_specimen","1"),),
            policy,DiagnosticResolution(variant["raster_resolution"],variant["raster_resolution"]),(finding,),
            assumptions=("Report-state contract specimen only; not actual NativeCore reconstruction fidelity.",),completion="failed"),)
    return view_set,{name:inputs[name] for name in ids},surface,settings,tuple(regions),tuple(anchors),upstream,data


def complete_report(report, manifest_hash, implementation, artifacts=()):
    existing = {finding.code for finding in report.findings}
    deferred = (("correction.plan_available","No D5 correction execution was qualified."),
                ("iteration.acceptance","No D6 accepted generation or promotion loop was evaluated."),
                ("qualification.human_review","Initial D7, real approved semantic pairs/provider fidelity and issue #84 remain open."),
                ("quality.export_verified","No D8 GLB delivery, topology or hidden-surface certification ran."))
    unknowns = tuple(Finding("deferred-"+code.replace(".","-"),code,"quality","info","unknown",
                            "Later-stage acceptance remains unknown.",reason=reason) for code,reason in deferred if code not in existing)
    findings = []
    for finding in report.findings:
        linked = tuple(Evidence("appearance-overlay-"+str(index),"artifact",
            "Actual D4 sampled colours/masks; white missing delta is unmeasured, not zero error.",tuple(a["view_ids"]),
            artifact=ArtifactReference("appearance-overlay-"+str(index),a["sha256"],a["media_type"],a["path"]))
            for index,a in enumerate(artifacts) if set(a.get("view_ids",[])) & set(finding.view_ids))
        findings.append(replace(finding,evidence=finding.evidence+linked))
    policy = replace(report.policy,policy_id="meshvenn.appearance-corpus",version=CORPUS_VERSION,
        configuration_sha256=sha256(canonical_json({"engine":report.policy.to_dict(),"manifest":manifest_hash,"implementation":implementation})),
        required_checks=tuple(sorted(set(report.policy.required_checks)|{f.code for f in unknowns})))
    result = replace(report,findings=tuple(findings)+unknowns,policy=policy,
                     engines=report.engines+(EngineVersion("appearance-corpus",CORPUS_VERSION),),
                     completion="partial" if report.completion=="complete" else report.completion)
    return replace(result,report_id="appearance-corpus-"+result.dependency_fingerprint[:20])


def failure_report(view_set,size,policy,error):
    failure = Finding("appearance-execution-failed","engine.appearance_execution","engine","error","unknown",
        "The actual D4 invocation raised; no quality success is established.",reason=error["error_type"]+": "+error["message"])
    return DiagnosticReport("appearance-execution-failed",view_set,(EngineVersion("appearance-corpus",CORPUS_VERSION),),
        policy.contract(),DiagnosticResolution(size,size),(failure,),completion="failed")


def resolution_observations(baseline,comparison):
    def regions(record):
        return {(r["region"]["view_id"],r["region"]["label"]):r for view in record.get("views",[]) for r in view["regions"]}
    left,right = regions(baseline),regions(comparison)
    entries = []
    tolerance = 1/max(1,baseline["raster_resolution"]-1)+1/max(1,comparison["raster_resolution"]-1)
    for key in sorted(set(left)|set(right)):
        a,b = left.get(key),right.get(key)
        aa,bb = a["region"]["bounds"] if a else None,b["region"]["bounds"] if b else None
        delta = max(abs(x-y) for x,y in zip(aa,bb)) if aa is not None and bb is not None else None
        entries.append({"view_id":key[0],"label":key[1],"baseline":a,"comparison":b,"normalized_bounds_delta":delta,
                        "normalized_sample_tolerance":tolerance,"bounds_within_tolerance":delta<=tolerance if delta is not None else None})
    localizations = []
    left_local = {r["view_id"]:r for r in baseline.get("localization",[])}
    right_local = {r["view_id"]:r for r in comparison.get("localization",[])}
    for view_id in sorted(set(left_local)|set(right_local)):
        a,b = left_local.get(view_id),right_local.get(view_id)
        aa = a.get("changed_bounds_normalized") if a else None
        bb = b.get("changed_bounds_normalized") if b else None
        delta = max(abs(x-y) for x,y in zip(aa,bb)) if aa is not None and bb is not None else None
        matched = (aa is None and bb is None) if delta is None else delta<=tolerance
        localizations.append({"view_id":view_id,"baseline":a,"comparison":b,"normalized_changed_bounds_delta":delta,
            "normalized_sample_tolerance":tolerance,"bounds_within_tolerance":matched})
    return {"regions":entries,"localization_checks":localizations,"actual_localization_baseline":baseline.get("localization",[]),
            "actual_localization_comparison":comparison.get("localization",[]),
            "matched_bounds_within_tolerance":all(item["bounds_within_tolerance"] is not False for item in entries) and
                                              all(item["bounds_within_tolerance"] for item in localizations)}


def run_qualification(root, output, *, selected_cases=(), split="all", quick=False):
    from core.appearance_diagnostics import AppearancePolicy, AppearanceResult, analyze_appearance
    started = perf_counter()
    manifest,manifest_hash = load_manifest(root)
    if set(selected_cases)-{case["case_id"] for case in manifest["cases"]}:
        raise ValueError("Unknown selected appearance case")
    cases = [case for case in manifest["cases"] if (not selected_cases or case["case_id"] in selected_cases) and
             (split=="all" or case["split"]==split)]
    if not cases:
        raise ValueError("Appearance selection contains no cases")
    policy_default = AppearancePolicy()
    implementation = implementation_provenance()
    identity = sha256(canonical_json({"manifest":manifest_hash,"implementation":implementation,"policy_defaults":jsonable(policy_default)}))
    output.mkdir(parents=True,exist_ok=True)
    index = 1
    while True:
        run_dir = output/"runs"/(identity[:16]+"-"+str(index))
        try:
            run_dir.mkdir(parents=True,exist_ok=False)
            break
        except FileExistsError:
            index += 1
    records,orders,sensitivity = [],[],[]
    for case in cases:
        case_records = []
        variants = case["variants"][:1] if quick else case["variants"]
        for variant in variants:
            size = variant["raster_resolution"]
            runs = ("canonical",) if quick else tuple(manifest["execution_plan"]["orders"])
            for order in runs:
                case_started = perf_counter()
                destination = run_dir/case["case_id"]/(str(size)+"-"+order)
                destination.mkdir(parents=True)
                view_set,inputs,surface,settings,regions,anchors,upstream,mesh_data = inputs_for_case(root,case,variant,order)
                policy = replace(policy_default,sampling_size=size,max_seconds=manifest["execution_plan"]["default_max_seconds_per_analysis"])
                mock = SemanticAdapterFixture(case["semantic_service"]["scenario"]) if case["scope"]=="adapter-only" else None
                record = {"case_id":case["case_id"],"split":case["split"],"scope":case["scope"],"raster_resolution":size,
                    "order":order,"input_order":list(view_set.input_order),"path":destination.relative_to(output).as_posix(),
                    "policy":jsonable(policy),"policy_sha256":sha256(canonical_json(jsonable(policy))),
                    "authored_region_anchors":jsonable(anchors),
                    "semantic_adapter":{"kind":"mock-adapter-only" if mock else "not-configured","scenario":case["semantic_service"]["scenario"],"real_provider_calls":0},
                    "upstream_kind":case["upstream"]["kind"] if case["upstream"] else None}
                try:
                    result = analyze_appearance(view_set,inputs,surface=surface,view_settings=settings,regions=regions,region_anchors=anchors,
                        upstream_reports=upstream,policy=policy,vision_analyzer=mock)
                    raw = result.to_json()
                    record["contract_roundtrip_passed"] = AppearanceResult.from_json(raw).to_json()==raw
                    raw_data = raw.encode("utf-8")
                    (destination/"appearance-result.json").write_bytes(raw_data)
                    original_report = result.report.to_json().encode("utf-8")
                    (destination/"engine-report.json").write_bytes(original_report)
                    artifacts = write_evidence(destination,result)
                    report = complete_report(result.report,manifest_hash,implementation,artifacts)
                    (destination/"diagnostic-report.json").write_bytes(report.to_json().encode("utf-8"))
                    metrics,states,pairs = raw_metrics(result)
                    localization = localization_metrics(variant,{"corpus_root":root},result)
                    upstream_findings = [finding.to_dict() for report0 in upstream for finding in report0.findings]
                    returned = {f.finding_id:f.to_dict() for f in result.report.findings}
                    upstream_original = [report0.to_dict() for report0 in upstream]
                    upstream_returned = [report0.to_dict() for report0 in result.upstream_reports]
                    upstream_hashes = [sha256(report0.to_json().encode("utf-8")) for report0 in upstream]
                    back = [i for i,label in enumerate(mesh_data["triangle_labels"]) if label=="body_back"]
                    visible = {triangle for view in result.views for triangle in view.visible_triangles}
                    record.update({"report":report.to_dict(),"verification_status":result.report.verification_status.value,
                        "identity_status":result.identity_status,"deterministic_status":result.deterministic_status,
                        "source_view_set_unchanged":result.report.view_set.dependency_fingerprint==view_set.dependency_fingerprint,
                        "engine_provenance":jsonable(result.provenance),"views":jsonable(result.views),"pairs":pairs,
                        "semantic":jsonable(result.semantic),"photometric_metrics":metrics,"visibility_states":states,
                        "localization":localization,"artifacts":artifacts,
                        "upstream_preservation":{"supplied_findings":upstream_findings,
                            "all_findings_equal":all(returned.get(f["finding_id"])==f for f in upstream_findings),
                            "all_reports_equal":upstream_original==upstream_returned,
                            "original_report_sha256":upstream_hashes,
                            "recorded_report_sha256":list(result.provenance.upstream_report_sha256),
                            "hashes_match":upstream_hashes==list(result.provenance.upstream_report_sha256),
                            "failure_gate_present":any(f.code=="quality.upstream_status" and f.status=="fail" for f in result.report.findings)},
                        "upstream_reports":upstream_returned,
                        "unobserved_subject":{"back_triangles":back,"visible_back_triangles":sorted(visible&set(back))},
                        "result_artifact":{"path":"appearance-result.json","sha256":sha256(raw_data),"bytes":len(raw_data),"kind":"actual_d4_full_strict_result"},
                        "engine_report_sha256":sha256(original_report)})
                except Exception as exc:
                    record["execution_failure"] = {"error_type":type(exc).__name__,"message":str(exc)}
                    report = complete_report(failure_report(view_set,size,policy,record["execution_failure"]),manifest_hash,implementation)
                    record["report"] = report.to_dict()
                    (destination/"diagnostic-report.json").write_bytes(report.to_json().encode("utf-8"))
                record["semantic_adapter"]["actual_local_mock_calls"] = mock.calls if mock else 0
                record["semantic_adapter"]["actual_timeout_arguments"] = mock.timeouts if mock else []
                record["elapsed_seconds"] = perf_counter()-case_started
                record["score"] = score_case(case,record)
                (destination/"analytic-source.json").write_bytes(checked_path(root,case["source"]["path"]).read_bytes())
                (destination/"authored-mesh.json").write_bytes(checked_path(root,case["mesh"]["path"]).read_bytes())
                for role,asset in variant["views"].items():
                    (destination/("original-"+role+".png")).write_bytes(checked_path(root,asset["path"]).read_bytes())
                (destination/"observation.json").write_bytes(canonical_json(record))
                records.append(record)
                case_records.append(record)
                print(f"{case['case_id']} {size} {order}: {'pass' if record['score']['passed'] else 'FAIL'} {record['score']['failures']}",flush=True)
        for variant in variants:
            group = [r for r in case_records if r["raster_resolution"]==variant["raster_resolution"]]
            baseline = next(r for r in group if r["order"]=="canonical")
            unique_orders = {tuple(r["input_order"]) for r in group}
            for record in group:
                if record is baseline:
                    continue
                orders.append({"case_id":case["case_id"],"raster_resolution":record["raster_resolution"],"order":record["order"],
                    "actual_input_order":record["input_order"],"distinct_orders_in_group":len(unique_orders),
                    "passed":semantic_signature(baseline["report"])==semantic_signature(record["report"])})
        canonical = [r for r in case_records if r["order"]=="canonical"]
        for record in canonical[1:]:
            baseline = canonical[0]
            sensitivity.append({"case_id":case["case_id"],"baseline_raster":baseline["raster_resolution"],"comparison_raster":record["raster_resolution"],
                "same_conclusions":semantic_signature(baseline["report"],bounds=False)==semantic_signature(record["report"],bounds=False),
                "both_satisfy_frozen_expectations":baseline["score"]["passed"] and record["score"]["passed"],
                "measurements":resolution_observations(baseline,record)})
    unchanged = implementation==implementation_provenance() and manifest_hash==load_manifest(root)[1]
    metrics = {}
    for scope in ("numeric-analytic","upstream-contract","adapter-only"):
        metrics[scope] = {}
        for partition in ("calibration","heldout"):
            selected = [r for r in records if r["scope"]==scope and r["split"]==partition]
            metrics[scope][partition] = {"evaluations":len(selected),"passed":sum(r["score"]["passed"] for r in selected),
                "failed":sum(not r["score"]["passed"] for r in selected),"assertions":sum(len(r["score"]["assertions"]) for r in selected),
                "missed_assertions":sum(len(r["score"]["failures"]) for r in selected),"execution_failures":sum("execution_failure" in r for r in selected),
                "abstentions":sum(len(r["score"]["abstentions"]) for r in selected)}
    passed = unchanged and all(r["score"]["passed"] for r in records) and all(check["passed"] for check in orders) and \
             all(check["both_satisfy_frozen_expectations"] and check["measurements"]["matched_bounds_within_tolerance"] for check in sensitivity)
    complete = not selected_cases and split=="all" and not quick
    summary = {"schema_version":SCHEMA_VERSION,"corpus_version":CORPUS_VERSION,"manifest_sha256":manifest_hash,
        "qualification_identity":identity,"implementation":implementation,"authorities_unchanged":unchanged,
        "qualification_status":"pass" if passed else "fail","complete_matrix":complete,
        "qualified_scope":"Frozen analytic observed-region colour/visibility subset" if passed and complete else "No full appearance matrix qualification established",
        "semantic_quality_qualified":False,"scope_limits":manifest["scope"],"metrics":metrics,"records":records,"order_checks":orders,
        "resolution_sensitivity":sensitivity,"elapsed_seconds":perf_counter()-started,"provider_calls":0,"network_calls":0,"paid_cost":0,
        "input_permutation_note":"Two source views permit two distinct permutations; reverse and rotate labels are the same actual order, explicitly recorded.",
        "run_path":run_dir.relative_to(output).as_posix(),"previous_attempts_retained":True}
    data = canonical_json(summary)
    (run_dir/"qualification.json").write_bytes(data)
    (output/"qualification.json").write_bytes(data)
    return summary
