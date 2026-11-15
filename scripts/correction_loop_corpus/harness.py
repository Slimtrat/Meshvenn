"""Run the real durable LoopRuntime with explicitly simulated trusted ports."""
from __future__ import annotations

import base64
from dataclasses import asdict
import json

from scripts.appearance_diagnostic_corpus.authoring import canonical_json,sha256
from .contract_sources import initialize_contract_source
from .ports import ObservationLog,SimulatedEvaluator,SimulatedProcessCrash,SimulatedProvider,TestClock
from .real_evidence import initialize_real_loop_source


def strict_state(data):
    from meshvenn_engine.core.correction_loop import LoopState
    return LoopState.from_dict({k:v for k,v in data.items() if k not in ("known_cost","cost_uncertain")})


def stop_reason(state):
    mapping={"attempt_budget_exhausted":"attempt_budget","elapsed_budget_exhausted":"time_budget",
        "response_deadline_exceeded":"time_budget","generation_cost_exhausted":"cost_budget",
        "provider_cost_ceiling_exceeded":"cost_budget","stalled_accepted_improvement":"stagnation",
        "accepted_improvement":"accepted","global_evaluation_unavailable":"evaluation_failure"}
    if state.status=="provider_unavailable":return "provider_unavailable"
    if state.status=="cancelled":return "cancelled"
    return next((mapping[r] for r in reversed(state.limitations) if r in mapping),state.status)


def execute_case(root,case,manifest,destination):
    from meshvenn_engine.loop_runtime import LoopRuntime
    destination.mkdir(parents=True,exist_ok=True)
    real_source=None
    if case["scope"]!="orchestration-only":
        context,real_source=initialize_real_loop_source(root)
    else:
        context=initialize_contract_source(root)
    context["include_provisional_mesh"]=case["case_id"]=="canonical_never_provisional_mesh"
    originals=context.get("original_files",{"photo":root/"assets/original-photo.png",
        "source":root/"original-source.json","glb":root/"assets/original.glb"})
    before={key:sha256(path.read_bytes()) for key,path in originals.items()}
    clock=TestClock(manifest["clock"]["initial_seconds"])
    log=ObservationLog()
    provider=SimulatedProvider(root,case,manifest,clock,log,real_source=real_source)
    evaluator=SimulatedEvaluator(root,case,context,clock,log,real_source=real_source)
    # Runtime roots are trusted host configuration. Keep their depth independent
    # of descriptive case names, while retaining the complete names in evidence.
    slot=manifest["cases"].index(case)
    store_root=destination.parent/"s"/f"{slot:02d}"
    runtime=LoopRuntime(store_root,provider,evaluator,clock)
    session=f"case-{slot:02d}"
    log.load_state=lambda:runtime.store.load(session)
    budget=case["budgets"]
    payload={"accepted":context["accepted"].to_dict(),
        "artifacts":{sha:base64.b64encode(data).decode() for sha,data in context["artifacts"].items()},
        "annotations":[a.to_dict() for a in context["annotations"]],
        "correction_policy":asdict(context["policy"]),"acceptance_policy":context["acceptance_policy"].to_dict(),
        "budget":{"max_attempts":budget["max_attempts"],"max_elapsed_seconds":budget["max_seconds"],
                  "max_cost":budget["max_cost"],"max_stagnation":budget["stagnation_limit"],
                  "request_timeout_seconds":min(budget["max_seconds"],10.)}}
    (destination/"start-payload.json").write_bytes(canonical_json(payload))
    result=runtime.execute("start",session,payload,cancel=lambda:log.cancelled)
    initial=strict_state(result)
    initial_plan_sha=sha256(initial.plans.to_json().encode())
    observed=set()
    promotions=[]
    def observe(data):
        state=strict_state(data)
        for event in state.events:
            if event.sequence in observed:continue
            observed.add(event.sequence)
            marker=log.event("machine_"+event.kind,sequence=event.sequence,request_id=event.request_id)
            if event.kind=="candidate_promoted":
                attempt=next(a for a in state.attempts if a.request.request_id==event.request_id)
                promotions.append({"candidate_sha256":attempt.decision.candidate_sha256,
                                   "event_index":marker["event_index"]})
        return state
    state=observe(result)
    restarted=False
    calls_after_restart=None
    expected_crash=False
    for step in range(40):
        if state.status in ("stopped","cancelled","provider_unavailable","needs_input","completion_uncertain","awaiting_host","awaiting_evaluator"):
            break
        try:
            result=runtime.execute("advance",session,{},cancel=lambda:log.cancelled)
        except SimulatedProcessCrash:
            expected_crash=True
            durable=runtime.store.load(session)
            (destination/"crash-durable-state.json").write_bytes(canonical_json(durable))
            count=len(log.provider_calls)
            fresh=LoopRuntime(store_root,provider,evaluator,clock)
            loaded=fresh.store.load(session)
            restarted=loaded==durable and bool(loaded.get("attempts")) and loaded["attempts"][-1]["status"]=="dispatching"
            runtime=fresh
            log.load_state=lambda:runtime.store.load(session)
            result=runtime.execute("resume",session,{},cancel=lambda:log.cancelled)
            observe(result)
            result=runtime.execute("advance",session,{},cancel=lambda:log.cancelled)
            calls_after_restart=len(log.provider_calls)-count
        state=observe(result)
    else:
        raise RuntimeError("Local harness bound exhausted before a quiescent loop stage")
    history=runtime.store.history(session)
    parsed=[strict_state(data) for data in history]
    state=strict_state(runtime.execute("status",session,{}))
    (destination/"last-state.json").write_text(state.to_json(),encoding="utf-8",newline="\n")
    (destination/"history.json").write_bytes(canonical_json(list(history)))
    (destination/"observed-events.json").write_bytes(canonical_json(log.events))
    (destination/"provider-receipts.json").write_bytes(canonical_json(log.returned_receipts))
    (destination/"evaluations.json").write_bytes(canonical_json(log.evaluations))
    after={key:sha256(runtime.store.read_artifact(value)) for key,value in before.items()}
    if any(sha256(path.read_bytes())!=before[key] for key,path in originals.items()):
        raise ValueError("An original fixture file was changed")
    receipt_times={r["receipt"]["request_id"]:r["received_seconds"] for r in log.returned_receipts}
    receipts=[]
    persisted_errors=[]
    candidate_hashes=[]
    candidate_meshes=[]
    valid=True
    for attempt in state.attempts:
        if attempt.error:
            phase="evaluation" if any(e.kind=="evaluation_failed" and e.request_id==attempt.request.request_id for e in state.events) else "provider"
            persisted_errors.append({"phase":phase,"request_id":attempt.request.request_id,"error":attempt.error})
        for receipt in attempt.receipts:
            valid=valid and receipt.request_id==attempt.request.request_id and receipt.request_sha256==attempt.request.sha256
            receipts.append({"request_id":receipt.request_id,"provider_id":receipt.provider_id,
                "model_id":receipt.model.engine_id,"parameters":json.loads(receipt.parameters_json),
                "usage":json.loads(receipt.usage.raw_json),"cost":receipt.usage.cost,
                "received_seconds":receipt_times.get(receipt.request_id,0.),"status":receipt.status})
            if receipt.error:persisted_errors.append({"phase":"provider","request_id":receipt.request_id,"error":receipt.error})
            if receipt.output_image:
                data=runtime.store.read_artifact(receipt.output_image.sha256)
                valid=valid and sha256(data)==receipt.output_image.sha256
                candidate_hashes.append(receipt.output_image.sha256)
        if attempt.evaluation:
            candidate_meshes.extend(a.artifact.sha256 for a in attempt.evaluation.candidate.artifacts if a.role in ("mesh","glb"))
    calls={c["request_id"] for c in log.provider_calls}
    dispatched={a.request.request_id for a in state.attempts}
    valid=valid and calls==dispatched and len(dispatched)==len(state.attempts)
    if case["provider_behavior"]!="crash_after_dispatch":
        # A different pre-receipt technical failure must not accidentally count
        # as exercising a cost, failure, cancellation or completed-provider case.
        returned={r["receipt"]["request_id"] for r in log.returned_receipts}
        persisted={r["request_id"] for r in receipts}
        valid=valid and calls==returned==persisted
    canonical=[s.accepted.view_set.canonical_reference.content.sha256 for s in parsed]
    canonical.extend(c["canonical_sha256"] for c in log.provider_calls)
    canonical.extend(e["canonical_sha256"] for e in log.evaluations)
    for attempt in state.attempts:
        canonical.extend(v.image.sha256 for v in attempt.request.prepared.prompt.references)
    decision=next((a.decision for a in reversed(state.attempts) if a.decision is not None),None)
    real=log.real_diagnostics.copy()
    appearance=real.pop("strict_appearance_result_json",None)
    if appearance:
        (destination/"real-appearance-result.json").write_text(appearance,encoding="utf-8",newline="\n")
    facts={"runtime_state_observed":True,"provider_calls":log.provider_calls,"evaluations":log.evaluations,
        "receipts":receipts,"promotions":promotions,"original_hashes_before":before,"original_hashes_after":after,
        "original_canonical_sha256":initial.accepted.view_set.canonical_reference.content.sha256,
        "canonical_history":canonical,"journal_bindings_valid":valid,"persisted_checkpoint_count":len(history),
        "initial_plan_sha256":initial_plan_sha,"final_plan_sha256":sha256(state.plans.to_json().encode()),
        "baseline_mean_iou":next((m.value for m in initial.accepted.metrics if m.name=="mean_iou"),None),
        "candidate_files_verified":bool(candidate_hashes) and all(runtime.store.has_artifact(v) for v in candidate_hashes),
        "candidate_sha256":candidate_hashes,"candidate_mesh_sha256":candidate_meshes,
        "cancel_event_index":log.cancel_event_index,"persisted_errors":persisted_errors,
        "restart_loaded_actual_store":restarted,"provider_calls_after_restart":calls_after_restart,
        "expected_simulated_crash_observed":expected_crash,"real_diagnostics":real,
        "final":{"promoted":state.accepted.sha256!=initial.accepted.sha256,"initial_sha256":initial.accepted.sha256,
            "accepted_sha256":state.accepted.sha256,"verification_status":decision.required_status if decision else state.verification_status,
            "attempt_count":len(state.attempts),"total_cost":state.known_cost,"cost_uncertain":state.cost_uncertain,
            "cancelled":state.status=="cancelled","provider_outcome_uncertain":bool(state.attempts and
                state.attempts[-1].status=="completion_uncertain"),"stop_reason":stop_reason(state),
            "status":state.status,"raw_stop_reasons":list(state.limitations)}}
    expected=manifest["port_metadata"]
    return {"facts":facts,"store_path":store_root.relative_to(destination.parent).as_posix(),
            "initial_state_sha256":sha256(initial.to_json().encode()),
            "final_state_sha256":sha256(state.to_json().encode()),"real_provider_calls":0,
            "provider_fidelity_qualified":False,"semantic_quality_qualified":False,
            "expected_port_metadata":{k:expected[k] for k in ("provider_id","model_id","parameters","usage")}}
