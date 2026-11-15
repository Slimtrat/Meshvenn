"""Durable adapter: reserve, release lock, perform an effect, retain receipts.

No provider is loaded implicitly. Service callbacks are trusted constructor
ports; host tools receive an outbox and supply bound receipts separately.
"""
from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from .errors import EngineError
from .loop_store import LoopStore
from .loop_runtime_ops import fields,payload_artifacts,port_artifacts,verify_snapshot,check_image,protected_pixels,inbox_append,inbox_load
from .core.diagnostic_contracts import EngineVersion
from .core.diagnostic_contracts.codec import fingerprint
from .core.correction_plans import CorrectionPolicy,EditAnnotation,ProviderCapabilities,plan_corrections
from .core.correction_loop import (LoopState,LoopSnapshot,LoopBudget,AcceptancePolicy,ProviderInfo,EvaluatorInfo,
    ProviderReceipt,ProviderResult,GlobalEvaluation,EvaluationResult,assess)
from .core.correction_loop.machine import event,stop,reserve,record_receipt,uncertain,current_attempt,replace_attempt,budget_reason,implementation_hash,TERMINAL


@lru_cache(maxsize=1)
def runtime_hash():
    digest=hashlib.sha256(implementation_hash().encode())
    for name in ("loop_runtime.py","loop_runtime_ops.py","loop_store.py"):
        digest.update(name.encode()+Path(__file__).resolve().with_name(name).read_bytes())
    return digest.hexdigest()


def loop_payload_schemas():
    from .catalogue import model_schema
    def obj(properties,required=()):return {"type":"object","properties":properties,"required":list(required),"additionalProperties":False}
    artifacts={"type":"object","maxProperties":128,"additionalProperties":{"type":"string"}}
    return {
        "start":obj({"accepted":model_schema(LoopSnapshot),"artifacts":artifacts,"budget":model_schema(LoopBudget),
            "acceptance_policy":model_schema(AcceptancePolicy),"capabilities":model_schema(ProviderCapabilities),
            "annotations":{"type":"array","maxItems":128,"items":model_schema(EditAnnotation)},
            "correction_policy":model_schema(CorrectionPolicy),"provider":model_schema(ProviderInfo)},("accepted",)),
        "status":obj({}),"cancel":obj({}),"resume":obj({}),
        "advance":obj({"plan_id":{"type":"string"}}),
        "supply":obj({"receipt":model_schema(ProviderReceipt),"artifacts":artifacts},("receipt",)),
        "artifact_read":obj({"sha256":{"type":"string"},"offset":{"type":"integer","minimum":0},"limit":{"type":"integer","minimum":1,"maximum":65536}},("sha256",)),
        "artifact_put":obj({"data_base64":{"type":"string"},"sha256":{"type":"string"}},("data_base64",)),
    }


class LoopRuntime:
    def __init__(self,root,provider=None,evaluator=None,clock=None):
        self.store=LoopStore(root)
        self.provider,self.evaluator=provider,evaluator
        self.clock=clock or time.time

    def _now(self):
        now=self.clock()
        from .core.correction_loop.models import finite
        finite(now,"runtime clock")
        return now

    def _result(self,state):
        data=state.to_dict()
        data.update(known_cost=state.known_cost,cost_uncertain=state.cost_uncertain)
        return data

    def _update(self,session,callback):
        def apply(data):return callback(LoopState.from_dict(data)).to_dict()
        return LoopState.from_dict(self.store.update(session,apply))

    def _load(self,session):return LoopState.from_dict(self.store.load(session))

    def _port_info(self):
        info=self.provider.metadata() if self.provider else None
        if info is not None and type(info) is not ProviderInfo:raise ValueError("Provider metadata must use the strict trusted port DTO.")
        return info

    def _evaluator_info(self):
        info=self.evaluator.metadata() if self.evaluator else None
        if info is not None and type(info) is not EvaluatorInfo:raise ValueError("Evaluator metadata must use the strict trusted port DTO.")
        return info

    def _current(self,state):
        if state.implementation_sha256!=implementation_hash() or state.runtime_sha256!=runtime_hash():
            raise ValueError("Stored loop implementation changed; inspect/migrate before any external effect.")
        info=self._port_info()
        if info is not None and info!=state.provider:raise ValueError("Provider configuration changed since the reserved session.")
        evaluation=self._evaluator_info()
        if state.evaluator is not None and evaluation!=state.evaluator:raise ValueError("Evaluator version changed since session creation.")

    def execute(self,operation,session_id,payload=None,*,cancel=None):
        payload={} if payload is None else payload
        if operation=="start":return self._result(self.start(session_id,payload,cancel=cancel))
        if operation=="artifact_put":
            fields(payload,("data_base64","sha256"),("data_base64",))
            raw=base64.b64decode(payload["data_base64"],validate=True)
            if len(raw)>64*1024*1024:raise ValueError("Artifact input exceeds 64MiB.")
            sha=self.store.put_artifact(raw,payload.get("sha256"))
            return {"schema_version":1,"verification_status":"unknown","sha256":sha,"bytes":len(raw)}
        if operation=="artifact_read":
            fields(payload,("sha256","offset","limit"),("sha256",))
            data=self.store.read_artifact(payload["sha256"])
            offset,limit=payload.get("offset",0),payload.get("limit",65536)
            if type(offset) is not int or type(limit) is not int or not 0<=offset<=len(data) or not 1<=limit<=65536:raise ValueError("Invalid loop artifact range.")
            chunk=data[offset:offset+limit]
            return {"schema_version":1,"verification_status":"unknown","sha256":payload["sha256"],"offset":offset,
                "bytes":len(chunk),"next_offset":offset+len(chunk),"total_bytes":len(data),
                "eof":offset+len(chunk)==len(data),"data_base64":base64.b64encode(chunk).decode()}
        if operation=="status":fields(payload,());return self._result(self._load(session_id))
        if operation=="cancel":
            fields(payload,())
            state=self._update(session_id,lambda s:stop(s,self._now(),"cancelled_by_host","cancelled"))
            return self._result(state)
        if operation=="supply":
            fields(payload,("receipt","artifacts"),("receipt",))
            state=self._load(session_id)
            self._current(state)
            if state.provider.execution_mode!="host_tool":raise ValueError("External receipts are accepted only for explicitly host-orchestrated tools.")
            payload_artifacts(self.store,payload.get("artifacts",{}))
            self._save_receipt(session_id,ProviderReceipt.from_dict(payload["receipt"]))
            return self._result(self._drain(session_id))
        if operation=="resume":fields(payload,());return self._result(self.resume(session_id,cancel=cancel))
        if operation=="advance":
            fields(payload,("plan_id",))
            if "plan_id" in payload and type(payload["plan_id"]) is not str:raise ValueError("Plan ID must be text.")
            return self._result(self.advance(session_id,payload.get("plan_id"),cancel=cancel))
        raise ValueError("Unknown loop operation.")

    def start(self,session,payload,*,cancel=None):
        started=self._now()
        fields(payload,("accepted","artifacts","budget","acceptance_policy","capabilities","annotations","correction_policy","provider"),("accepted",))
        accepted=LoopSnapshot.from_dict(payload["accepted"])
        payload_artifacts(self.store,payload.get("artifacts",{}))
        verify_snapshot(self.store,accepted)
        info=self._port_info()
        declared=ProviderInfo.from_dict(payload["provider"]) if "provider" in payload else None
        capabilities=ProviderCapabilities.from_dict(payload["capabilities"]) if "capabilities" in payload else ProviderCapabilities()
        if info is not None:
            if declared is not None and declared!=info:raise ValueError("Remote provider metadata cannot override a trusted service port.")
            if "capabilities" in payload and capabilities!=info.capabilities:raise ValueError("Provider capabilities mismatch.")
        elif declared is not None:
            if declared.execution_mode!="host_tool":raise ValueError("A remote payload cannot configure a service generation API.")
            info=declared
        else:info=ProviderInfo("unavailable",EngineVersion("unavailable","unconfigured"),capabilities,execution_mode="unavailable")
        annotations=tuple(EditAnnotation.from_dict(a) for a in payload.get("annotations",[]))
        policy=CorrectionPolicy(**payload.get("correction_policy",{}))
        plans=plan_corrections(accepted.view_set,accepted.reports,capabilities=info.capabilities,annotations=annotations,policy=policy,cancel=cancel)
        now=self._now()
        status="provider_unavailable" if info.execution_mode=="unavailable" else "ready"
        state=LoopState(session,accepted,plans,LoopBudget.from_dict(payload.get("budget",{})),
            AcceptancePolicy.from_dict(payload.get("acceptance_policy",{})),info,self._evaluator_info(),annotations,policy,
            implementation_hash(),started,now,status,runtime_sha256=runtime_hash())
        state=event(state,now,"session_created","Accepted artifacts are immutable content-addressed evidence.")
        if cancel and cancel():state=stop(state,now,"cancelled_by_host","cancelled")
        self.store.create(session,state.to_dict())
        return state

    def _save_receipt(self,session,receipt):
        state=self._load(session)
        attempt=current_attempt(state)
        if attempt is None or receipt.request_id!=attempt.request.request_id or receipt.request_sha256!=attempt.request.sha256:
            raise ValueError("Stale provider response; it cannot enter this attempt's inbox.")
        if receipt.output_image:self.store.read_artifact(receipt.output_image.sha256)
        if receipt.receipt_evidence:self.store.read_artifact(receipt.receipt_evidence.sha256)
        inbox_append(self.store,receipt.request_id,"receipt",receipt.to_dict())

    def _drain(self,session):
        state=self._load(session)
        if state.implementation_sha256!=implementation_hash() or state.runtime_sha256!=runtime_hash():
            return state  # A new implementation may inspect, but not replay old decisions implicitly.
        attempt=current_attempt(state)
        if attempt is None:return state
        for data in inbox_load(self.store,attempt.request.request_id,"receipt"):
            receipt=ProviderReceipt.from_dict(data)
            current=current_attempt(state)
            if any(r.sha256==receipt.sha256 for r in (*current.receipts,*current.rejected_receipts)):
                continue
            try:state=self._update(session,lambda s:record_receipt(s,receipt,self._now()))
            except ValueError as exc:
                message="Invalid provider receipt retained: "+str(exc)
                def reject(s):
                    a=current_attempt(s)
                    if any(r.sha256==receipt.sha256 for r in a.rejected_receipts):return s
                    s=replace_attempt(s,replace(a,rejected_receipts=(*a.rejected_receipts,receipt)))
                    if a.completed_receipt or a.status in TERMINAL or s.status in ("cancelled","stopped"):
                        return event(s,self._now(),"invalid_receipt_retained",message[:1024],request_id=a.request.request_id)
                    return uncertain(s,self._now(),message)
                state=self._update(session,reject)
        for data in inbox_load(self.store,attempt.request.request_id,"evaluation"):
            state=self._finalize(session,GlobalEvaluation.from_dict(data))
        return state

    def _dispatch(self,session,request,*,recover=False,cancel=None):
        if cancel and cancel():return self._update(session,lambda s:stop(s,self._now(),"cancelled_by_host","cancelled"))
        state=self._load(session)
        if state.status in ("cancelled","stopped") and not recover:return state
        callback=self.provider.recover if recover else self.provider.submit
        try:
            outcome=callback(request,artifacts=self.store.read_artifact,
                timeout_seconds=max(.001,request.expires_at-self._now()) if not recover else state.budget.request_timeout_seconds,cancel=cancel)
            if type(outcome) is not ProviderResult:raise ValueError("Provider returned an invalid port result.")
            port_artifacts(self.store,outcome.artifacts)
            self._save_receipt(session,outcome.receipt)
            if cancel and cancel():self._update(session,lambda s:stop(s,self._now(),"cancelled_by_host","cancelled"))
            return self._drain(session)
        except Exception as exc:
            # Once dispatch is reserved, an exception is NOT proof of no charge.
            return self._update(session,lambda s:uncertain(s,self._now(),type(exc).__name__+": "+str(exc)[:900]))

    def advance(self,session,plan_id=None,*,cancel=None):
        state=self._drain(session)
        self._current(state)
        if cancel and cancel():return self._update(session,lambda s:stop(s,self._now(),"cancelled_by_host","cancelled"))
        attempt=current_attempt(state)
        if state.status in ("cancelled","stopped"):return state
        reason=budget_reason(state,self._now())
        if reason:return self._update(session,lambda s:stop(s,self._now(),reason))
        if attempt and attempt.status=="candidate_ready":return self._evaluate(session,cancel=cancel)
        if attempt and attempt.status not in TERMINAL:return state
        effect=[]
        def reserve_once(s):
            updated,request=reserve(s,self._now(),plan_id)
            if request is not None:effect.append(request)
            return updated
        state=self._update(session,reserve_once)
        if not effect:return state
        request=effect[0]
        if request.provider.execution_mode=="host_tool":return state
        if self.provider is None:return self._update(session,lambda s:uncertain(s,self._now(),"Reserved service port is unavailable; no automatic resubmission."))
        return self._dispatch(session,request,cancel=cancel)

    def resume(self,session,*,cancel=None):
        state=self._drain(session)
        if not state.attempts and state.status in ("cancelled","stopped"):
            return state
        info=self._port_info()
        evaluation=self._evaluator_info()
        if not state.attempts and info is not None and state.provider.execution_mode=="unavailable":
            def bind(s):
                if s.attempts or s.status in ("cancelled","stopped") or s.provider.execution_mode!="unavailable":
                    return s
                now=self._now()
                reason=budget_reason(s,now)
                if reason:return stop(s,now,reason)
                plans=plan_corrections(s.accepted.view_set,s.accepted.reports,capabilities=info.capabilities,annotations=s.annotations,policy=s.correction_policy)
                return event(replace(s,provider=info,evaluator=evaluation,plans=plans),now,"ports_bound","Explicit resume bound a configured trusted host port.",status="ready")
            state=self._update(session,bind)
        elif state.evaluator is None and evaluation is not None:
            state=self._update(session,lambda s:event(replace(s,evaluator=evaluation),self._now(),"evaluator_bound","A replayable local evaluator is now configured."))
        if not state.attempts and state.status in ("cancelled","stopped"):
            return state
        self._current(state)
        attempt=current_attempt(state)
        if cancel and cancel():return self._update(session,lambda s:stop(s,self._now(),"cancelled_by_host","cancelled"))
        reason=budget_reason(state,self._now())
        if reason:state=self._update(session,lambda s:stop(s,self._now(),reason))
        if attempt is None:return state
        if attempt.terminal_receipt is not None and not attempt.cost_uncertain and state.status in ("cancelled","stopped"):
            return state
        if attempt.status in ("candidate_ready","evaluating") and state.status not in ("cancelled","stopped"):
            return self._evaluate(session,cancel=cancel)
        if attempt.status not in ("dispatching","pending","completion_uncertain","awaiting_host"):return state
        state=self._update(session,lambda s:uncertain(s,self._now(),"Recovered pending work; provider completion must be reconciled before any new paid submission."))
        if self.provider is None or not state.provider.supports_recovery:return state
        effect=[]
        def reserve_query(s):
            a=current_attempt(s)
            if a.recovery_queries>=s.budget.max_recovery_queries:return stop(s,self._now(),"recovery_query_budget_exhausted")
            effect.append(a.request)
            return event(replace_attempt(s,replace(a,recovery_queries=a.recovery_queries+1)),self._now(),"recovery_query_reserved","Read-only completion reconciliation; never another submit.",request_id=a.request.request_id)
        state=self._update(session,reserve_query)
        return self._dispatch(session,effect[0],recover=True,cancel=cancel) if effect else state

    def _evaluate(self,session,*,cancel=None):
        effect=[]
        def reserve_eval(s):
            if s.status in ("cancelled","stopped"):return s
            reason=budget_reason(s,self._now())
            if reason:return stop(s,self._now(),reason)
            a=current_attempt(s)
            if a is None or a.status not in ("candidate_ready","evaluating"):return s
            if self.evaluator is None:return replace(s,status="awaiting_evaluator")
            effect.append(a)
            return event(replace_attempt(s,replace(a,status="evaluating")),self._now(),"global_evaluation_started","Reevaluate the complete candidate view set and usage profile.",request_id=a.request.request_id,status="evaluating")
        state=self._update(session,reserve_eval)
        if not effect:return state
        attempt=effect[0]
        receipt=attempt.completed_receipt
        try:
            original=attempt.request.prepared.prompt.original.image
            check_image(self.store,receipt.output_image,dimensions=(original.width,original.height))
            result=self.evaluator.evaluate(attempt.request,receipt.output_image,artifacts=self.store.read_artifact,
                timeout_seconds=max(.001,state.started_at+state.budget.max_elapsed_seconds-self._now()),cancel=cancel)
            if type(result) is not EvaluationResult:raise ValueError("Evaluator returned an invalid result.")
            if result.evaluation.evaluator!=state.evaluator:raise ValueError("Evaluator identity changed.")
            port_artifacts(self.store,result.artifacts)
            verify_snapshot(self.store,result.evaluation.candidate)
            target=next((v for v in result.evaluation.candidate.view_set.views if v.view_id==attempt.request.plan.target.view_id),None)
            if target is None or target.image is None or target.image.sha256!=receipt.output_image.sha256:raise ValueError("Evaluation did not evaluate the actual provider image.")
            inbox_append(self.store,attempt.request.request_id,"evaluation",result.evaluation.to_dict())
            if cancel and cancel():self._update(session,lambda s:stop(s,self._now(),"cancelled_by_host","cancelled"))
            return self._drain(session)
        except Exception as exc:
            def failed(s):
                a=current_attempt(s)
                return stop(event(replace_attempt(s,replace(a,status="rejected",error=str(exc)[:1024])),self._now(),
                    "evaluation_failed",type(exc).__name__+": "+str(exc)[:900],request_id=a.request.request_id),self._now(),"global_evaluation_unavailable")
            return self._update(session,failed)

    def _finalize(self,session,evaluation):
        def finalize(s):
            self._current(s)
            a=current_attempt(s)
            if a is None or evaluation.request_id!=a.request.request_id or evaluation.request_sha256!=a.request.sha256:
                raise ValueError("Late evaluation belongs to another request.")
            if a.decision is not None:return s
            if s.status in ("cancelled","stopped") or budget_reason(s,self._now()):
                return event(replace_attempt(s,replace(a,evaluation=evaluation,status="late")),self._now(),"late_evaluation_retained","Accepted artifacts are unchanged.",request_id=a.request.request_id)
            decision=assess(s.accepted,a.request,evaluation,s.acceptance_policy,
                protected_pixels=protected_pixels(self.store,a.request,evaluation.candidate,s.acceptance_policy))
            updated=replace(a,evaluation=evaluation,decision=decision,status="accepted" if decision.promoted else "rejected")
            result=replace_attempt(s,updated)
            if decision.promoted:
                plans=plan_corrections(evaluation.candidate.view_set,evaluation.candidate.reports,capabilities=s.provider.capabilities,policy=s.correction_policy)
                return event(replace(result,accepted=evaluation.candidate,plans=plans,annotations=()),self._now(),"candidate_promoted",
                    "Measured improvement passed all required global and protected-evidence checks.",request_id=a.request.request_id,status="stopped",
                    limitations=tuple(dict.fromkeys((*s.limitations,"accepted_improvement"))))
            result=event(result,self._now(),"candidate_rejected",", ".join(decision.reasons),request_id=a.request.request_id,
                stagnation_count=s.stagnation_count+1,status="ready")
            reason=budget_reason(result,self._now(),new_request=True)
            return stop(result,self._now(),reason) if reason else result
        return self._update(session,finalize)
