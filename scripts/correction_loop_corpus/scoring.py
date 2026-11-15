"""Independent frozen controls on observable runtime, journal and port facts.

The adapter must derive these normalized facts from actual state/receipts; it
must never copy the case's expected outcome into a verdict or promotion flag.
"""
from __future__ import annotations


def score_case(case, record):
    facts=record.get("facts",{})
    calls=facts.get("provider_calls",[])
    evaluations=facts.get("evaluations",[])
    receipts=facts.get("receipts",[])
    final=facts.get("final",{})
    original=facts.get("original_hashes_before",{})
    after=facts.get("original_hashes_after",{})
    limits=case["budgets"]
    assertions=[]
    checks=[check for evaluation in evaluations for check in evaluation.get("checks",[])]
    def has_check(code,status):
        return any(c["code"]==code and c["status"]==status and c.get("required") is True for c in checks)
    for control in case["expected"]["controls"]:
        passed=False
        if control=="original_photo_and_source_bytes_unchanged":
            passed=all(original.get(k) and original[k]==after.get(k) for k in ("photo","source"))
        elif control=="original_GLB_artifact_bytes_unchanged":
            passed=bool(original.get("glb")) and original["glb"]==after.get("glb")
        elif control in ("canonical_reference_unchanged","canonical_hash_identical_for_every_call","provisional_mesh_never_reference"):
            expected=facts.get("original_canonical_sha256")
            observed=facts.get("canonical_history",[])
            passed=bool(expected and observed) and all(value==expected for value in observed)
            if control=="provisional_mesh_never_reference":
                passed=passed and all(value not in set(facts.get("candidate_mesh_sha256",[])) for value in observed)
        elif control=="attempts_and_receipts_journalled":
            passed=facts.get("journal_bindings_valid") is True and facts.get("persisted_checkpoint_count",0)>0
        elif control=="no_real_provider_or_model_quality_qualification":
            passed=record.get("real_provider_calls")==0 and record.get("provider_fidelity_qualified") is False and \
                   record.get("semantic_quality_qualified") is False
        elif control=="never_promote_before_global_evaluation":
            promotions=facts.get("promotions",[])
            passed=facts.get("runtime_state_observed") is True and all(any(
                e["candidate_sha256"]==p["candidate_sha256"] and e["event_index"]<p["event_index"] and
                e.get("all_required_pass") is True for e in evaluations) for p in promotions)
        elif control=="provider_called":
            passed=bool(calls)
        elif control=="global_evaluation_ran":
            passed=bool(evaluations)
        elif control=="promoted_after_full_reevaluation":
            passed=final.get("promoted") is True and bool(facts.get("promotions")) and \
                   any(e.get("all_required_pass") is True for e in evaluations)
        elif control=="accepted_candidate_is_measured_candidate":
            passed=bool(final.get("accepted_sha256")) and any(e["candidate_sha256"]==final["accepted_sha256"] and
                    e.get("all_required_pass") is True for e in evaluations)
        elif control=="higher_mean_retained":
            baseline=facts.get("baseline_mean_iou")
            passed=baseline is not None and any(e.get("mean_iou") is not None and e["mean_iou"]>baseline for e in evaluations)
        elif control=="named_part_failure_retained":
            passed=has_check("geometry.important_part","fail")
        elif control=="required_identity_failure_retained":
            passed=has_check("appearance.identity_assessment","fail")
        elif control=="required_unknown_retained":
            passed=any(c.get("required") is True and c["status"]=="unknown" for c in checks)
        elif control=="no_unknown_to_pass_coercion":
            passed=final.get("verification_status") in ("unknown","fail") and final.get("promoted") is False
        elif control in ("not_promoted","late_candidate_not_promoted"):
            passed=final.get("promoted") is False and not facts.get("promotions")
        elif control=="rollback_restores_initial_asset":
            passed=bool(final.get("initial_sha256")) and final["initial_sha256"]==final.get("accepted_sha256")
        elif control=="candidate_materialized_separately":
            passed=facts.get("candidate_files_verified") is True and bool(facts.get("candidate_sha256")) and \
                   all(sha not in set(original.values()) for sha in facts["candidate_sha256"])
        elif control=="photo_source_GLB_hashes_exact":
            passed={"photo","source","glb"}<=set(original) and original==after
        elif control in ("attempt_limit_respected","bounded_calls"):
            passed=len(calls)<=limits["max_attempts"] and final.get("attempt_count",-1)>=len(calls)
        elif control=="exactly_two_provider_calls":
            passed=len(calls)==2
        elif control=="exactly_one_provider_call":
            passed=len(calls)==1
        elif control in ("time_limit_respected","no_new_call_after_deadline"):
            passed=bool(calls) and all(c.get("dispatch_seconds") is not None and c["dispatch_seconds"]<limits["max_seconds"] for c in calls)
        elif control=="cost_limit_respected":
            passed=final.get("total_cost") is not None and final["total_cost"]<=limits["max_cost"] and \
                   sum(r.get("cost",0.) for r in receipts)<=limits["max_cost"]
        elif control=="cost_reservation_precedes_dispatch":
            passed=bool(calls) and all(c.get("cost_reserved_before_dispatch") is True for c in calls)
        elif control=="budget_stop_explicit":
            passed=final.get("stop_reason") in ("attempt_budget","time_budget","cost_budget")
        elif control=="stagnation_stop_explicit":
            passed=final.get("stop_reason")=="stagnation" and len(calls)<=limits["stagnation_limit"]
        elif control=="failure_journalled":
            passed=bool(facts.get("persisted_errors"))
        elif control=="late_receipt_retained":
            passed=bool(receipts) and any(r.get("received_seconds",0)>limits["max_seconds"] for r in receipts)
        elif control=="cost_not_erased":
            passed=bool(receipts) and final.get("total_cost") is not None and \
                   final["total_cost"]>=sum(r.get("cost",0.) for r in receipts)
        elif control=="cancelled_state_retained":
            passed=final.get("cancelled") is True
        elif control=="no_new_call_after_cancel":
            index=facts.get("cancel_event_index")
            passed=index is not None and all(c["event_index"]<index for c in calls)
        elif control=="durable_pending_before_dispatch":
            passed=bool(calls) and all(c.get("durable_pending_before_dispatch") is True for c in calls)
        elif control=="restart_reads_actual_journal":
            passed=facts.get("restart_loaded_actual_store") is True
        elif control=="uncertain_attempt_not_redispatched":
            passed=facts.get("provider_calls_after_restart")==0 and len(calls)==1
        elif control=="explicit_uncertainty_retained":
            passed=final.get("provider_outcome_uncertain") is True and final.get("cost_uncertain") is True
        elif control=="no_provider_dispatch":
            passed=not calls and facts.get("runtime_state_observed") is True
        elif control=="local_plans_preserved":
            passed=bool(facts.get("initial_plan_sha256")) and facts["initial_plan_sha256"]==facts.get("final_plan_sha256")
        elif control=="provider_unavailable_explicit":
            passed=final.get("stop_reason")=="provider_unavailable"
        elif control=="provider_model_params_usage_preserved":
            expected=record.get("expected_port_metadata",{})
            passed=bool(receipts) and bool(expected) and all(all(r.get(k)==expected.get(k) for k in
                ("provider_id","model_id","parameters","usage")) for r in receipts)
        elif control=="receipt_request_binding_exact":
            ids={c["request_id"] for c in calls}
            passed=bool(receipts) and len(ids)==len(calls) and all(r.get("request_id") in ids for r in receipts)
        elif control=="all_dispatches_auditable":
            passed=bool(calls) and facts.get("journal_bindings_valid") is True and len(receipts)==len(calls)
        elif control=="real_preflight_and_appearance_ran":
            real=facts.get("real_diagnostics",{})
            passed=real.get("preflight_calls",0)>0 and real.get("appearance_calls",0)>0 and bool(real.get("raw_report_sha256"))
        elif control=="numeric_region_improves_fail_to_pass":
            passed=facts.get("real_diagnostics",{}).get("numeric_improved") is True
        elif control=="real_identity_stays_unknown":
            passed=facts.get("real_diagnostics",{}).get("identity_status")=="unknown"
        elif control=="receipt_survives_evaluation_failure":
            passed=bool(receipts) and any(e.get("phase")=="evaluation" for e in facts.get("persisted_errors",[]))
        else:
            raise ValueError("Unhandled frozen loop control: "+control)
        assertions.append({"name":control,"passed":bool(passed)})
    failures=[a["name"] for a in assertions if not a["passed"]]
    if record.get("execution_failure"):
        failures.append("unexpected_runtime_or_adapter_failure")
    return {"passed":not failures,"assertions":assertions,"failures":failures}
