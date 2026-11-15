"""Local instrumented ports; these qualify no real provider or model."""
from __future__ import annotations

from pathlib import Path
import json

from scripts.appearance_diagnostic_corpus.authoring import sha256
from .contract_sources import capabilities,simulated_candidate


class SimulatedProcessCrash(BaseException):
    """An intentionally uncaught process-loss stand-in after dispatch."""


class TestClock:
    def __init__(self,initial=0.):
        self.value=float(initial)

    def __call__(self):
        return self.value

    def advance(self,seconds):
        self.value+=seconds


class ObservationLog:
    def __init__(self):
        self.events=[]
        self.provider_calls=[]
        self.evaluations=[]
        self.returned_receipts=[]
        self.cancelled=False
        self.cancel_event_index=None
        self.load_state=None
        self.real_diagnostics={}

    def event(self,kind,**data):
        value={"event_index":len(self.events)+1,"kind":kind,**data}
        self.events.append(value)
        return value


def library_types():
    # The standalone facade maps core under meshvenn_engine.core. Construct its
    # exact DTO classes at this port boundary; no duck-typed fake result escapes.
    from meshvenn_engine.core.correction_loop import models,ports
    from meshvenn_engine.core.diagnostic_contracts import ArtifactReference,EngineVersion
    from meshvenn_engine.core.correction_plans import ProviderCapabilities
    return models,ports,ArtifactReference,EngineVersion,ProviderCapabilities


class SimulatedProvider:
    def __init__(self,root,case,manifest,clock,log,*,real_source=None):
        self.root,self.case,self.manifest,self.clock,self.log=root,case,manifest,clock,log
        self.real_source=real_source

    def metadata(self):
        models,_,_,EngineVersion,Capabilities=library_types()
        meta=self.manifest["port_metadata"]
        mode="unavailable" if self.case["provider_behavior"]=="unavailable" else "service_api"
        cap=Capabilities.from_dict(capabilities().to_dict())
        return models.ProviderInfo(meta["provider_id"],EngineVersion(meta["model_id"],meta["model_version"]),cap,
            execution_mode=mode,parameters_json=json.dumps(meta["parameters"],sort_keys=True,separators=(",",":")),
            max_cost_per_request=self.case["options"].get("quote_cost",meta["default_quote_cost"]),
            supports_recovery=False,supports_idempotency=False,simulation=True)

    def submit(self,request,*,artifacts,timeout_seconds,cancel=None):
        models,port,ArtifactReference,_,_=library_types()
        durable=self.log.load_state() if self.log.load_state else {}
        attempt=durable.get("attempts",[])[-1] if durable.get("attempts") else {}
        identity=attempt.get("request",{})
        current=durable.get("accepted",{}).get("view_set",{}).get("canonical_reference") or {}
        call=self.log.event("provider_dispatch",request_id=request.request_id,dispatch_seconds=self.clock(),
            canonical_sha256=(current.get("content") or {}).get("sha256"),
            durable_pending_before_dispatch=attempt.get("status") in ("dispatching","pending") and identity.get("request_id")==request.request_id,
            cost_reserved_before_dispatch=identity.get("max_cost")==request.max_cost and attempt.get("status")=="dispatching")
        self.log.provider_calls.append(call)
        behavior=self.case["provider_behavior"]
        if behavior=="crash_after_dispatch":
            raise SimulatedProcessCrash("Intentional local process-loss specimen after the durable dispatch reservation")
        self.clock.advance(self.case["options"].get("provider_clock_advance",0.))
        outcomes=self.case["evaluation_outcomes"]
        outcome=outcomes[min(request.attempt_number-1,len(outcomes)-1)] if outcomes else "no_progress"
        if self.real_source:
            data=self.real_source["candidate_png"]
        else:
            data=(self.root/("assets/candidate-erased-part.png" if outcome=="higher_mean_part_failure" else
                             "assets/candidate-improved.png")).read_bytes()
        meta=self.manifest["port_metadata"]
        usage=models.Usage(self.case["options"].get("receipt_cost",.2),"USD",
                           meta["usage"]["input_units"],meta["usage"]["output_units"],meta["usage"]["images"],
                           json.dumps(meta["usage"],sort_keys=True,separators=(",",":")))
        failed=behavior=="service_error"
        receipt=models.ProviderReceipt(request.request_id,request.sha256,request.provider.provider_id,request.provider.model,
            "failed" if failed else "completed",usage,
            None if failed else ArtifactReference("simulated-output-"+str(request.attempt_number),sha256(data),"image/png"),
            "local-operation-"+str(request.attempt_number),request.provider.parameters_json,
            error="Local simulated service failure; no real service was contacted." if failed else "")
        self.log.returned_receipts.append({"receipt":receipt.to_dict(),"received_seconds":self.clock()})
        self.log.event("provider_return",request_id=request.request_id,receipt_sha256=receipt.sha256)
        if behavior=="cancel_during_call":
            self.log.cancelled=True
            self.log.cancel_event_index=self.log.event("cancel_requested")["event_index"]
        return port.ProviderResult(receipt,() if failed else ((sha256(data),data),))

    def recover(self,*args,**kwargs):
        raise AssertionError("This specimen advertises no recovery; an uncertain request must never be resubmitted")


class SimulatedEvaluator:
    def __init__(self,root,case,context,clock,log,*,real_source=None):
        self.root,self.case,self.context,self.clock,self.log=root,case,context,clock,log
        self.real_source=real_source

    def metadata(self):
        models,_,_,EngineVersion,_=library_types()
        return models.EvaluatorInfo(EngineVersion("corpus.real_D2_D4_recheck" if self.real_source else
                                   "corpus.simulated_global_evaluator","1"),simulation=self.real_source is None)

    def evaluate(self,request,output_image,*,artifacts,timeout_seconds,cancel=None):
        models,port,_,_,_=library_types()
        outcomes=self.case["evaluation_outcomes"]
        outcome=outcomes[min(request.attempt_number-1,len(outcomes)-1)] if outcomes else "no_progress"
        event=self.log.event("evaluation_started",request_id=request.request_id,candidate_image_sha256=output_image.sha256)
        reader=artifacts if callable(artifacts) else artifacts.read_artifact
        payload=reader(output_image.sha256)
        if sha256(payload)!=output_image.sha256:
            raise ValueError("The evaluator did not receive the exact provider image bytes")
        if outcome=="evaluation_error":
            raise RuntimeError("Local evaluator failure after a real simulated provider receipt was durably recorded")
        if self.real_source:
            from .real_evidence import evaluate_real_candidate
            if output_image.sha256!=sha256(self.real_source["candidate_png"]):
                raise ValueError("The real diagnostic control received an unexpected candidate image")
            result=evaluate_real_candidate(self.real_source,derived_from=request.prepared.derived_from)
            snapshot=self.context["real_snapshot_factory"](result,request)
            generated=()
            self.log.real_diagnostics={"preflight_calls":1,"appearance_calls":1,
                "raw_reports":[r.to_dict() for r in result["reports"]],
                "raw_report_sha256":[sha256(r.to_json().encode()) for r in result["reports"]],
                "numeric_improved":result["numeric_improved"],"identity_status":result["identity_status"],
                "strict_appearance_result_json":result["appearance"].to_json()}
        else:
            snapshot,generated=simulated_candidate(self.context,request,output_image,self.root,outcome)
        self.clock.advance(self.case["options"].get("evaluation_clock_advance",0.))
        candidate=models.LoopSnapshot.from_dict(snapshot.to_dict())
        checks=[{"code":f.code,"status":f.status.value,"required":f.required or f.code in r.policy.required_checks}
                for r in snapshot.reports for f in r.findings]
        mean=next((m.value for m in snapshot.metrics if m.name=="mean_iou"),None)
        returned=self.log.event("evaluation_returned",request_id=request.request_id,candidate_sha256=candidate.sha256)
        observation={**event,"event_index":returned["event_index"],"candidate_sha256":candidate.sha256,"candidate_image_sha256":output_image.sha256,
            "mean_iou":mean,"checks":checks,"all_required_pass":bool(checks) and all(
                c["status"]=="pass" for c in checks if c["required"]),
            "canonical_sha256":candidate.view_set.canonical_reference.content.sha256,
            "reports":[r.to_dict() for r in candidate.reports]}
        self.log.evaluations.append(observation)
        evaluation=models.GlobalEvaluation(request.request_id,request.sha256,candidate,self.metadata(),
                                            tuple(v.view_id for v in candidate.view_set.views))
        return port.EvaluationResult(evaluation,generated)
