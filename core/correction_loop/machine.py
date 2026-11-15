"""Pure transitions; external effects are reserved before the host performs them."""
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
import hashlib
import json

from ..diagnostic_contracts.codec import fingerprint
from ..correction_plans import plan_corrections,prepare_correction
from .models import GenerationRequest,LoopAttempt,LoopEvent

TERMINAL=("accepted","rejected","failed","not_submitted","late")


@lru_cache(maxsize=1)
def implementation_hash():
    root=Path(__file__).resolve().parent.parent
    paths=[p for name in ("correction_loop","correction_plans","diagnostic_contracts") for p in (root/name).glob("*.py")]
    digest=hashlib.sha256()
    for p in sorted(paths): digest.update(p.relative_to(root).as_posix().encode()+b"\0"+p.read_bytes())
    return digest.hexdigest()


def event(state,now,kind,detail,*,request_id=None,**changes):
    at=max(now,state.last_at)
    events=(*state.events,LoopEvent(len(state.events)+1,at,kind,detail,request_id))
    return replace(state,last_at=at,events=events,**changes)


def stop(state,now,reason,status="stopped"):
    if state.status=="cancelled":status="cancelled"
    if state.status==status and reason in state.limitations:return state
    return event(state,now,"loop_stopped",reason,status=status,limitations=tuple(dict.fromkeys((*state.limitations,reason))))


def current_attempt(state):
    return state.attempts[-1] if state.attempts else None


def replace_attempt(state,attempt):
    if not state.attempts or state.attempts[-1].request.request_id!=attempt.request.request_id:
        raise ValueError("Attempt no longer owns the active request.")
    return replace(state,attempts=(*state.attempts[:-1],attempt))


def budget_reason(state,now,*,new_request=False):
    if now<state.last_at:return "clock_regression"
    if now-state.started_at>=state.budget.max_elapsed_seconds:return "elapsed_budget_exhausted"
    if state.known_cost>state.budget.max_cost:return "generation_cost_exhausted"
    if new_request:
        if len(state.attempts)>=state.budget.max_attempts:return "attempt_budget_exhausted"
        if state.stagnation_count>=state.budget.max_stagnation:return "stalled_accepted_improvement"
        if state.cost_uncertain:return "provider_usage_uncertain"
        quote=state.provider.max_cost_per_request
        if quote is None:return "provider_cost_ceiling_unknown"
        if state.provider.cost_unit!=state.budget.cost_unit:return "provider_cost_unit_mismatch"
        if state.known_cost+quote>state.budget.max_cost:return "generation_cost_exhausted"
    return None


def reserve(state,now,plan_id=None):
    if state.status in ("stopped","cancelled"):return state,None
    attempt=current_attempt(state)
    if attempt and attempt.status not in TERMINAL:return state,None
    if state.implementation_sha256!=implementation_hash():return stop(state,now,"implementation_changed"),None
    if state.provider.execution_mode=="unavailable":return replace(state,status="provider_unavailable"),None
    reason=budget_reason(state,now,new_request=True)
    if reason:return stop(state,now,reason),None
    plans=plan_corrections(state.accepted.view_set,state.accepted.reports,capabilities=state.provider.capabilities,
        annotations=state.annotations,policy=state.correction_policy)
    ready=[p for p in plans.plans if p.readiness=="ready" and (plan_id is None or p.plan_id==plan_id)]
    if plans.completion!="complete" or not ready:
        return event(replace(state,plans=plans),now,"input_required","No supported current local plan can be executed.",status="needs_input"),None
    plan=ready[0]
    prepared=prepare_correction(plan,state.accepted.view_set,state.accepted.reports,capabilities=state.provider.capabilities,
        annotations=state.annotations,policy=state.correction_policy)
    number=len(state.attempts)+1
    identity=fingerprint({"session":state.session_id,"attempt":number,"accepted":state.accepted.sha256,
        "plan":plan.dependency_fingerprint,"provider":state.provider.to_dict()})
    request=GenerationRequest("request-"+identity[:32],identity,state.session_id,number,state.accepted.sha256,
        plan,prepared,state.provider,state.provider.max_cost_per_request,
        min(state.started_at+state.budget.max_elapsed_seconds,now+state.budget.request_timeout_seconds))
    stage="awaiting_host" if state.provider.execution_mode=="host_tool" else "dispatching"
    attempt=LoopAttempt(request,stage)
    result=event(replace(state,plans=plans),now,"request_reserved","Request identity and cost ceiling persisted before any external effect.",
        request_id=request.request_id,attempts=(*state.attempts,attempt),status="awaiting_host" if stage=="awaiting_host" else "pending")
    return result,request


def record_receipt(state,receipt,now):
    attempt=current_attempt(state)
    if attempt is None or receipt.request_id!=attempt.request.request_id or receipt.request_sha256!=attempt.request.sha256:
        raise ValueError("Stale or unrelated provider response.")
    if any(r.sha256==receipt.sha256 for r in attempt.receipts):return state
    request=attempt.request
    if receipt.provider_id!=request.provider.provider_id or receipt.model!=request.provider.model:
        raise ValueError("Provider/model differs from the reserved request.")
    if receipt.status in ("pending","completed") and fingerprint(json.loads(receipt.parameters_json))!=fingerprint(json.loads(request.provider.parameters_json)):
        raise ValueError("Provider parameters differ from the reserved request.")
    if receipt.usage.cost_unit!=state.budget.cost_unit:raise ValueError("Usage cost unit differs from the reserved budget.")
    updated=replace(attempt,receipts=(*attempt.receipts,receipt))
    state=replace_attempt(state,updated)
    if attempt.status in TERMINAL or state.status in ("cancelled","stopped"):
        return event(state,now,"late_receipt_retained","Response and actual usage retained without changing accepted artifacts.",request_id=request.request_id)
    reason=budget_reason(state,now)
    if now>=request.expires_at or reason:
        state=replace_attempt(state,replace(updated,status="late"))
        return stop(event(state,now,"late_response","The response is retained but cannot be promoted under current limits.",request_id=request.request_id),
                    now,reason or "response_deadline_exceeded")
    if updated.known_cost>request.max_cost:
        return stop(state,now,"provider_cost_ceiling_exceeded")
    if receipt.status=="completed":stage,status="candidate_ready","candidate_ready"
    elif receipt.status=="pending":
        # An older pending acknowledgement cannot overwrite an already complete image.
        if attempt.completed_receipt:return state
        stage,status="pending","pending"
    elif receipt.status=="unknown":stage,status="completion_uncertain","completion_uncertain"
    else:stage,status=receipt.status,"ready"
    state=replace_attempt(state,replace(updated,status=stage))
    return event(state,now,"provider_receipt",receipt.status,request_id=request.request_id,status=status,
        stagnation_count=state.stagnation_count+int(stage in ("failed","not_submitted")))


def uncertain(state,now,message):
    attempt=current_attempt(state)
    if attempt is None:return state
    if attempt.status in TERMINAL:return state
    updated=replace(attempt,status="completion_uncertain",error=message[:1024])
    return event(replace_attempt(state,updated),now,"provider_completion_uncertain",message[:1024],
        request_id=attempt.request.request_id,status=state.status if state.status in ("cancelled","stopped") else "completion_uncertain")
