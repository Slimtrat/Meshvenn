"""Frozen author expectations applied to actual D4 evidence, not fixture names."""
from __future__ import annotations


def semantic_signature(report, *, bounds=True):
    return sorted((f["code"],f["status"],tuple(sorted(f["view_ids"])),
                   tuple(sorted((r["view_id"],r["label"],tuple(r["bounds"] or ()) if bounds else ()) for r in f["regions"])),
                   tuple(sorted((a["kind"],tuple(sorted(a["view_ids"]))) for a in f["proposed_actions"])))
                  for f in report.get("findings",[]))


def all_regions(record):
    return [r for view in record.get("views",[]) for r in view["regions"]]


def subject_regions(case, record):
    return [r for r in all_regions(record) if r["region"]["label"]==case["expected"]["region_label"]]


def _finding(record, code, status=None):
    return [f for f in record.get("report",{}).get("findings",[]) if f["code"]==code and (status is None or f["status"]==status)]


def _unknown_subject(case, record):
    regions = subject_regions(case,record)
    if regions:
        return all(r["color_status"]=="unknown" for r in regions)
    return bool(_finding(record,"appearance.color_consistency","unknown"))


def score_case(case, record):
    expected = case["expected"]
    regions = subject_regions(case,record)
    semantic = record.get("semantic") or {}
    findings = record.get("report",{}).get("findings",[])
    assertions = []
    def add(name, passed, **evidence):
        assertions.append({"name":name,"passed":bool(passed),"evidence":evidence})
    if case["surface_region"]["surface_label"] == "body_back":
        unseen = record.get("unobserved_subject",{})
        subject_status = "unknown" if unseen.get("back_triangles") and not unseen.get("visible_back_triangles") and \
                         _finding(record,"appearance.surface_coverage","unknown") else None
        add("authored_named_region_status",subject_status in expected["named_region_status"],observed_status=subject_status)
    elif regions:
        add("authored_named_region_status",all(r["color_status"] in expected["named_region_status"] for r in regions),
            observed=[{"view_id":r["region"]["view_id"],"status":r["color_status"],"comparable":r["comparable_samples"],
                       "changed":r["changed_samples"]} for r in regions])
    else:
        add("authored_named_region_status","unknown" in expected["named_region_status"] and _unknown_subject(case,record),
            observed_status="unknown" if _unknown_subject(case,record) else None)
    for control in expected["required_controls"]:
        passed = False
        evidence = {}
        if control == "original_input_integrity_checked":
            seen = {entry[0] for entry in record.get("engine_provenance",{}).get("image_fingerprints",[])}
            passed = {"reference","target"} <= seen or any(f["category"]=="input" for f in findings)
        elif control in ("semantic_quality_unknown_without_real_approved_analyzer","semantic_quality_not_qualified"):
            passed = record.get("identity_status")=="unknown" and not (semantic.get("metadata") or {}).get("qualification_evidence")
        elif control == "no_automatic_correction":
            passed = record.get("source_view_set_unchanged") is True
        elif control == "observed_named_region_numeric_pass":
            passed = bool(regions) and all(r["color_status"]=="pass" and r["comparable_samples"]>0 for r in regions)
        elif control == "observed_named_region_numeric_fail":
            passed = bool(regions) and any(r["color_status"]=="fail" and r["changed_samples"]>0 for r in regions)
        elif control == "localized_failure_overlaps_authored_region":
            overlaps = record.get("localization",[])
            passed = any(item["intersection_pixels"]>0 for item in overlaps)
            evidence = {"localization":overlaps}
        elif control == "unaffected_shared_region_numeric_pass":
            unaffected = [r for r in all_regions(record) if r["region"]["label"]=="unaffected_shared_region"]
            passed = bool(unaffected) and all(r["color_status"]=="pass" and r["comparable_samples"]>0 for r in unaffected)
        elif control == "no_unsupported_colour_fault_attribution":
            passed = not any(r["color_status"]=="fail" for r in regions)
        elif control == "unavailable_named_region_unknown":
            passed = _unknown_subject(case,record) if case["surface_region"]["surface_label"]!="body_back" else \
                     bool(record.get("unobserved_subject",{}).get("back_triangles")) and \
                     not record.get("unobserved_subject",{}).get("visible_back_triangles") and \
                     bool(_finding(record,"appearance.surface_coverage","unknown"))
        elif control == "unverified_camera_unknown":
            passed = _unknown_subject(case,record) and any(f["category"]=="camera" and f["status"]=="unknown" for f in findings)
        elif control == "ambiguous_surface_correspondence_unknown":
            passed = _unknown_subject(case,record) and record.get("visibility_states",{}).get("ambiguous",0)>0
        elif control == "declared_scalar_gain_used":
            target = next((v for v in record.get("views",[]) if v["view_id"]=="target"),None)
            deltas = record.get("photometric_metrics",{})
            passed = target is not None and target["settings"]["photometry"]=="calibrated" and \
                     target["settings"]["linear_gain"]==.65 and deltas.get("corrected_mean_delta") is not None and \
                     deltas.get("raw_mean_delta") is not None and deltas["corrected_mean_delta"] < deltas["raw_mean_delta"]
        elif control == "raw_photometric_difference_retained":
            passed = (record.get("photometric_metrics",{}).get("raw_mean_delta") or 0)>0
        elif control == "true_colour_unknown_under_uncontrolled_lighting":
            passed = _unknown_subject(case,record) and not _finding(record,"appearance.color_consistency","fail")
        elif control in ("circular_or_target_derived_reference_rejected","reference_cannot_self_validate_target"):
            passed = _unknown_subject(case,record) and not _finding(record,"appearance.canonical_reference","pass")
        elif control == "accepted_design_ancestor_reference_usable":
            passed = any(pair.get("reference_eligibility") in ("accepted","accepted_design") for pair in record.get("pairs",[])) or \
                     bool(_finding(record,"appearance.canonical_reference","pass"))
        elif control in ("stale_content_reference_detected","input_failure_not_erased"):
            passed = any(f["category"]=="input" and f["status"]=="fail" for f in findings)
        elif control == "same_upstream_geometry_fail_preserved":
            preservation = record.get("upstream_preservation",{})
            passed = preservation.get("all_reports_equal") is True and preservation.get("hashes_match") is True and \
                     preservation.get("failure_gate_present") is True
        elif control == "overall_verification_cannot_pass":
            passed = record.get("verification_status")=="fail"
        elif control == "actual_numeric_engine_still_evaluated":
            passed = bool(record.get("pairs")) and any(r["comparable_samples"]>0 for r in all_regions(record))
        elif control == "semantic_mock_adapter_scope_only":
            passed = record.get("semantic_adapter",{}).get("kind")=="mock-adapter-only" and \
                     record["semantic_adapter"]["real_provider_calls"]==0 and record["semantic_adapter"].get("actual_local_mock_calls",0)>0
        elif control == "service_unavailable_unknown":
            passed = semantic.get("state") in ("unavailable","service_error") and record.get("identity_status")=="unknown"
        elif control == "malformed_response_rejected":
            passed = semantic.get("state")=="malformed_response" and bool(semantic.get("error_code"))
        elif control == "conflicting_claims_preserved_and_unknown":
            claims = semantic.get("claims",[])
            passed = any(c["status"]=="unknown" and {r["verdict"] for r in c["claims"]} >= {"consistent","changed"} for c in claims)
        elif control == "unsupported_claim_unknown":
            claims = semantic.get("claims",[])
            passed = bool(claims) and all(c["status"]=="unknown" for c in claims)
        elif control == "valid_mock_contract_preserved":
            passed = semantic.get("state")=="complete" and bool(semantic.get("raw_response_sha256")) and bool(semantic.get("metadata"))
        else:
            raise ValueError("Unknown frozen appearance control: " + control)
        add(control,passed,**evidence)
    failures = [a["name"] for a in assertions if not a["passed"]]
    if record.get("execution_failure") or record.get("contract_roundtrip_passed") is False:
        failures.append("actual_execution_or_contract_failure")
    return {"passed":not failures,"assertions":assertions,"failures":failures,
            "subject_region_statuses":[r["color_status"] for r in regions],
            "abstentions":[{"code":f["code"],"view_ids":f["view_ids"],"reason":f["reason"]} for f in findings if f["status"]=="unknown"]}
