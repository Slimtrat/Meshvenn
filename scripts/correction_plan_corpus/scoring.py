"""Frozen acceptance controls applied to measured plans and exact packages."""
from __future__ import annotations


def signature(result):
    """All plan/package content; opaque context IDs remain separately recorded."""
    return sorted((p["action_kind"],p["readiness"],str(p["target"]),
                   str(p["required_controls"]),str(p["unsupported_controls"]),
                   str(p["prompt"]),str(p["evidence"])) for p in result.get("plans",[]))


def score_case(case, record):
    result = record.get("result",{})
    plans = result.get("plans",[])
    edits = [p for p in plans if p["action_kind"]=="edit_region"]
    ready = [p for p in edits if p["readiness"]=="ready"]
    findings = [f for r in record.get("reports",[]) for f in r["findings"]]
    upstream = record.get("upstream",{})
    prepared = record.get("prepared",[])
    annotations = result.get("annotations",[])
    assertions = []
    def has(code,status=None):
        return any(f["code"]==code and (status is None or f["status"]==status) for f in findings)
    def workflow(kind):
        return any(p["action_kind"]==kind for p in plans)
    def unsupported(control):
        return any(control in p["unsupported_controls"] and p["readiness"]=="unsupported" and p["alternative"] for p in edits)
    def no_drop(control):
        return bool(edits) and all(control in p["required_controls"] for p in edits)
    for control in case["expected"]["controls"]:
        passed = False
        if control=="originals_unchanged":
            passed = record.get("source_unchanged") is True
        elif control=="all_plans_bind_exact_sources_reports_policy_and_capabilities":
            passed = record.get("dependency_bindings_passed") is True and record.get("contract_roundtrip_passed") is True
        elif control=="no_provider_execution":
            passed = record.get("provider_execution_calls")==0
        elif control=="no_general_semantic_or_human_qualification":
            passed = result.get("verification_status")=="unknown" and record.get("provider_fidelity_qualified") is False and \
                     all(p["verification_status"]=="unknown" for p in prepared)
        elif control=="actual_local_D4_failure":
            passed = upstream.get("kind")=="actual_D4" and has("appearance.color_consistency","fail")
        elif control=="eligible_targeted_plan":
            passed = bool(ready)
        elif control=="edit_has_bounded_region_and_accepted_reference":
            passed = bool(ready) and all(p["target"] and p["target"]["bounds"] and p["prompt"]["references"] and
                p["target"]["view_id"]=="target" for p in ready)
        elif control=="explicit_D2_D3_D4_postconditions":
            passed = bool(edits) and all({"rerun_preflight","rerun_geometry","rerun_appearance"} <=
                                        {c["kind"] for c in p["prompt"]["postconditions"]} for p in edits)
        elif control=="prepare_is_nonexecuting_package":
            passed = bool(prepared) and all(p["candidate_origin"]=="derived" and p["prompt"]["preserve_originals"] for p in prepared)
        elif control=="actual_named_D4_pass":
            passed = upstream.get("kind")=="actual_D4" and any(r["region"]["label"]=="shared_patch" and r["color_status"]=="pass"
                for view in upstream.get("views",[]) for r in view["regions"])
        elif control in ("no_image_edit_without_supported_fault","no_symmetry_correction",
                         "no_image_regeneration_for_framing","no_image_regeneration_for_mask",
                         "no_image_edit_for_engine_failure","no_unsupported_targeted_edit",
                         "no_autoregeneration_for_missing_semantics","no_autoregeneration_for_low_confidence"):
            passed = not edits
        elif control=="actual_alignment_proposal":
            passed = upstream.get("kind")=="actual_D2" and upstream.get("alignment_proposals",0)>0
        elif control=="preparation_workflow":
            passed = workflow("prepare_alignment")
        elif control=="actual_mask_failure":
            passed = has("input.empty_mask","fail") or has("input.alpha_mask_mismatch","fail")
        elif control=="mask_preparation_workflow":
            passed = workflow("repair_mask")
        elif control=="actual_coverage_failure":
            passed = has("coverage.insufficient","fail")
        elif control=="useful_view_workflow":
            passed = workflow("request_view")
        elif control=="requested_direction_is_missing_observation":
            camera = case["author_intent"]["required_camera"]
            passed = any(p["prompt"]["camera"] and
                p["prompt"]["camera"]["requested_azimuth_degrees"]==camera["azimuth_degrees"] and
                p["prompt"]["camera"]["requested_elevation_degrees"]==camera["elevation_degrees"]
                for p in plans if p["action_kind"]=="request_view")
        elif control=="actual_native_failure":
            passed = upstream.get("kind")=="actual_native_failure" and has("engine.native_failure") and \
                     bool(upstream.get("native_library_sha256"))
        elif control=="engine_diagnosis_workflow":
            passed = workflow("diagnose_engine")
        elif control=="actual_ambiguous_geometry":
            passed = upstream.get("kind")=="actual_D3" and has("geometry.attribution","unknown")
        elif control=="reference_choice_workflow":
            passed = workflow("select_reference")
        elif control=="actual_canonical_geometry_evidence":
            passed = upstream.get("kind")=="actual_D3" and has("geometry.reference_conflict","fail")
        elif control=="canonical_evidence_retained":
            passed = any(e["code"]=="geometry.reference_conflict" for p in plans for e in p["evidence"])
        elif control=="no_unsupported_global_blame":
            eligible = {vid for f in findings if f["code"]=="geometry.reference_conflict" and f["status"]=="fail" for vid in f["view_ids"]}
            passed = all(p["target"] and p["target"]["view_id"] in eligible and p["prompt"]["annotation"] for p in edits)
        elif control=="eligible_edit_intent_preserved":
            passed = bool(edits) and all(p["target"] and p["prompt"]["references"] for p in edits)
        elif control=="unsupported_masks_explicit":
            passed = unsupported("mask")
        elif control=="no_silent_mask_drop":
            passed = no_drop("mask") and bool(annotations) and all(p["prompt"]["annotation"] and
                p["prompt"]["annotation"]["mask"] in [a["mask"] for a in annotations] for p in edits)
        elif control=="not_prepared_for_provider":
            passed = not prepared and not ready
        elif control=="at_least_two_accepted_references":
            passed = bool(edits) and all(len(p["prompt"]["references"])>=2 for p in edits)
        elif control=="unsupported_multiple_references_explicit":
            passed = unsupported("multiple_references")
        elif control=="no_silent_reference_drop":
            accepted = set(record.get("accepted_reference_ids",[]))
            passed = len(accepted)>=2 and bool(edits) and all(accepted<={v["view_id"] for v in p["prompt"]["references"]} for p in edits)
        elif control=="unsupported_camera_explicit":
            passed = unsupported("camera_request")
        elif control=="no_silent_camera_drop":
            passed = no_drop("camera_request") and all(p["prompt"]["camera"] and p["prompt"]["camera"]["camera"] and
                                                       not p["prompt"]["camera"]["compliance_guaranteed"] for p in edits)
        elif control=="base_plan_preparable":
            passed = bool(ready) and bool(prepared)
        elif control.startswith("prepare_rejects_stale_"):
            mutation = record.get("prepare_mutation",{})
            passed = mutation.get("kind")==control.removeprefix("prepare_rejects_stale_") and \
                     mutation.get("mutation_constructed") is True and mutation.get("prepare_called") is True and \
                     mutation.get("rejected") is True and mutation.get("error_type")=="ValueError"
        elif control=="user_original_preserved":
            passed = bool(prepared) and all(p["prompt"]["original"]["origin"]=="user" and p["prompt"]["preserve_originals"] for p in prepared) and \
                     record.get("source_unchanged") is True
        elif control=="candidate_lineage_is_derived_from_original":
            target_sha = record.get("target_original_sha256")
            passed = bool(target_sha) and bool(prepared) and all(target_sha in p["derived_from"] and p["candidate_origin"]=="derived" for p in prepared)
        elif control=="actual_semantic_unknown":
            passed = upstream.get("identity_status")=="unknown"
        elif control=="actual_local_semantic_mock_called":
            passed = upstream.get("semantic_mock_calls",0)>0 and bool(upstream.get("semantic_claims")) and all(
                claim["status"]=="unknown" for claim in upstream["semantic_claims"])
        else:
            raise ValueError("Unhandled frozen correction control: "+control)
        assertions.append({"name":control,"passed":bool(passed)})
    failures = [a["name"] for a in assertions if not a["passed"]]
    if record.get("execution_failure"):
        failures.append("execution_failure")
    expected_technical_partial = case["source"]["kind"]=="actual_native_failure" and \
        result.get("completion")=="partial" and not edits and not prepared
    if result.get("completion")!="complete" and not expected_technical_partial:
        failures.append("planning_incomplete")
    return {"passed":not failures,"assertions":assertions,"failures":failures}
