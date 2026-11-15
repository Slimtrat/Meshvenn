"""Orchestration simulations only: no provider, vision or asset qualification."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"lib"))
from meshvenn_engine.loop_runtime import LoopRuntime
from meshvenn_engine.core.correction_loop import (AcceptancePolicy,EvaluatorInfo,EvaluationResult,
    GlobalEvaluation,LoopBudget,LoopSnapshot,ProviderInfo,ProviderReceipt,ProviderResult,SnapshotArtifact,Usage)
from meshvenn_engine.core.correction_plans import ProviderCapabilities
from meshvenn_engine.core.diagnostic_contracts import (ArtifactReference,CameraDeclaration,CanonicalReference,
    DiagnosticPolicy,DiagnosticReport,DiagnosticResolution,EngineVersion,Evidence,Finding,Measurement,
    Region,ViewRevision,ViewSetRevision)
from meshvenn_engine.core.diagnostics_preflight import RasterInput


PROOF=ArtifactReference("test-author-proof","a"*64,"application/json")
CAPS=ProviderCapabilities("test-provider","1",("region_edit","mask","multiple_references","camera_request","identity_reference"))
MODEL=EngineVersion("test.simulated_provider","1")
TEST_ENGINE=EngineVersion("test.simulated_global_check","1")
REGION=Region("target","authored-local-change",(12/31,12/31,19/31,19/31))


@contextmanager
def temporary_directory():
    temporary=tempfile.TemporaryDirectory()
    if os.name=="nt":
        from meshvenn_engine.loop_store import _windows_path
        path=Path(_windows_path(temporary.name))
    else:path=Path(temporary.name)
    try:yield path
    finally:
        # The sandbox's Windows TEMP can itself exceed 130 characters. Keep
        # cleanup in the same extended namespace as the real store operations.
        shutil.rmtree(path)
        temporary.cleanup()


def image(changed):
    def chunk(kind,data):return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    rows=[]
    for y in reversed(range(32)):
        row=bytearray(b"\0")
        for x in range(32):
            color=(160,30,40,255) if changed and 12<=x<20 and 12<=y<20 else (40,130,80,255)
            row.extend(color if 4<=x<28 and 4<=y<28 else (0,0,0,0))
        rows.append(bytes(row))
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",32,32,8,6,0,0,0))+
            chunk(b"IDAT",zlib.compress(b"".join(rows)))+chunk(b"IEND",b""))


def glb(tag):
    document=json.dumps({"asset":{"version":"2.0","generator":tag}},separators=(",",":")).encode()
    document+=b" "*((-len(document))%4)
    return struct.pack("<4sIII4s",b"glTF",2,20+len(document),len(document),b"JSON")+document


def artifact(name,data,media="application/octet-stream"):
    return ArtifactReference(name,hashlib.sha256(data).hexdigest(),media)


def declared_report(view_set,initial=False):
    codes=(("appearance.color_consistency","fail"),("appearance.coverage","pass")) if initial else (("test.global_ok","pass"),)
    findings=[]
    for index,(code,status) in enumerate(codes):
        evidence=Evidence("e-"+str(index),"observation","Declared orchestration simulation; no model or physical quality is qualified.",
            ("target",),(REGION,),measurements=(Measurement("test_support",64,"sample"),))
        findings.append(Finding("f-"+str(index),code,"appearance","warning",status,
            "Contract fixture only.",("target",),(REGION,),evidence=(evidence,)))
    return DiagnosticReport("report-"+str(view_set.revision),view_set,(TEST_ENGINE,),
        DiagnosticPolicy("test.loop.profile","1","b"*64,tuple(code for code,_ in codes)),
        DiagnosticResolution(32,32),tuple(findings))


def fixture():
    original,candidate=image(True),image(False)
    before_glb,source=glb("original untouched"),b'{"original_source":"unchanged"}'
    def view(name,data,role):
        raster=RasterInput.from_png_bytes(data)
        return ViewRevision(name,1,raster.content_reference(),None,
            CameraDeclaration("orthographic",0.,0.,False,True,PROOF),role=role)
    target,reference=view("target",original,"observation"),view("reference",candidate,"reference")
    revision=ViewSetRevision("loop-review",1,(target,reference),CanonicalReference("accepted",1,reference.image,True,("reference",),PROOF))
    artifacts=(SnapshotArtifact("glb",artifact("original-glb",before_glb,"model/gltf-binary")),
               SnapshotArtifact("source_state",artifact("original-source",source,"application/json")))
    snapshot=LoopSnapshot("original",revision,(declared_report(revision,True),),
        (Measurement("target_error",1.,"normalized_error"),),artifacts)
    values=(original,candidate,before_glb,source)
    payload={"accepted":snapshot.to_dict(),"artifacts":{hashlib.sha256(v).hexdigest():base64.b64encode(v).decode() for v in values},
        "acceptance_policy":AcceptancePolicy(required_checks=("test.global_ok",),required_engines=(TEST_ENGINE.engine_id,)).to_dict()}
    return snapshot,payload


class Provider:
    """Strict lib-namespace test port; submit logs a simulated paid effect."""
    def __init__(self,log,mode="pending",hook=None):self.log,self.mode,self.hook=Path(log),mode,hook
    def metadata(self):return ProviderInfo("test-provider",MODEL,CAPS,parameters_json='{"strength":0.25,"quality":"bounded"}',
        max_cost_per_request=.25,supports_recovery=True,simulation=True)
    def _reply(self,request,kind):
        with self.log.open("ab") as stream:stream.write((kind+" "+request.request_id+"\n").encode())
        if kind=="submit" and self.mode=="interrupt":raise SystemExit("Interrupted after the reserved external effect.")
        completed=kind=="submit" and self.mode!="pending"
        content=image(False)
        output=artifact("candidate-image",content,"image/png") if completed else None
        model=EngineVersion(MODEL.engine_id,"unexpected") if self.mode=="invalid-model" and kind=="submit" else MODEL
        params='{"strength":0.9}' if self.mode=="invalid-parameters" and kind=="submit" else request.provider.parameters_json
        if self.mode=="equivalent-parameters":params=' { "quality": "bounded", "strength": 0.25 } '
        unit="credits" if self.mode=="invalid-usage-unit" and kind=="submit" else "USD"
        cost=2. if self.mode=="cost-overrun" and kind=="submit" else .2 if completed else .1
        receipt=ProviderReceipt(request.request_id,request.sha256,"test-provider",model,
            "completed" if completed else "pending",Usage(cost,unit),output,parameters_json=params)
        if self.hook and kind=="submit":self.hook(request)
        return ProviderResult(receipt,((output.sha256,content),) if output else ())
    def submit(self,request,**kwargs):return self._reply(request,"submit")
    def recover(self,request,**kwargs):return self._reply(request,"recover")


class Evaluator:
    def __init__(self,before,log,*,canonical_change=False,hook=None,version="1"):
        self.before,self.log,self.canonical_change,self.hook,self.version=before,Path(log),canonical_change,hook,version
    def metadata(self):return EvaluatorInfo(EngineVersion("test.local_evaluator",self.version),simulation=True)
    def evaluate(self,request,output_image,**kwargs):
        with self.log.open("ab") as stream:stream.write(b"evaluate\n")
        old=self.before.view_set
        target=next(v for v in old.views if v.view_id=="target")
        target=replace(target,revision=2,image=RasterInput.from_png_bytes(image(False)).content_reference(),
            origin="derived",derived_from=request.prepared.derived_from)
        canonical=replace(old.canonical_reference,revision=2) if self.canonical_change else old.canonical_reference
        views=replace(old,revision=2,views=tuple(target if v.view_id=="target" else v for v in old.views),canonical_reference=canonical)
        candidate_glb=glb("candidate artifact")
        new_glb=artifact("candidate-glb",candidate_glb,"model/gltf-binary")
        snapshot=LoopSnapshot("candidate",views,(declared_report(views),),
            (Measurement("target_error",.5,"normalized_error"),),tuple(
                SnapshotArtifact("glb",new_glb) if a.role=="glb" else a for a in self.before.artifacts))
        result=EvaluationResult(GlobalEvaluation(request.request_id,request.sha256,snapshot,self.metadata(),
            tuple(v.view_id for v in old.views)),((new_glb.sha256,candidate_glb),))
        if self.hook:self.hook(request)
        return result


def advance_process(root,log,barrier,queue):
    try:
        runtime=LoopRuntime(root,provider=Provider(log),clock=lambda:1000.)
        barrier.wait(8)
        queue.put(runtime.advance("session").status)
    except Exception as exc:queue.put(repr(exc))


class LoopRuntimeAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.folder=self.enterContext(temporary_directory())
        self.now=[1000.]
        self.before,self.payload=fixture()
        self.log,self.eval_log=self.folder/"provider.log",self.folder/"evaluator.log"
    def runtime(self,provider=None,evaluator=None):
        return LoopRuntime(self.folder/"store",provider=provider,evaluator=evaluator,clock=lambda:self.now[0])
    def calls(self,kind):
        return sum(line.startswith(kind+" ") for line in self.log.read_text().splitlines()) if self.log.exists() else 0
    def unchanged(self,runtime,state):
        self.assertEqual(state.accepted.sha256,self.before.sha256)
        for item in self.before.artifacts:
            expected=glb("original untouched") if item.role=="glb" else b'{"original_source":"unchanged"}'
            self.assertEqual(runtime.store.read_artifact(item.artifact.sha256),expected)

    def test_two_advance_processes_reserve_only_one_paid_submission(self):
        runtime=self.runtime(Provider(self.log))
        runtime.start("session",self.payload)
        context=multiprocessing.get_context("spawn")
        barrier,queue=context.Barrier(2),context.Queue()
        self.addCleanup(queue.close)
        processes=[context.Process(target=advance_process,args=(str(runtime.store.root),str(self.log),barrier,queue)) for _ in range(2)]
        for process in processes:process.start();self.addCleanup(self.stop,process)
        for process in processes:process.join(12);self.assertEqual(process.exitcode,0)
        self.assertEqual([queue.get(timeout=2),queue.get(timeout=2)],["pending","pending"])
        self.assertEqual(self.calls("submit"),1)
        self.assertEqual(len(runtime._load("session").attempts),1)

    @staticmethod
    def stop(process):
        if process.is_alive():process.terminate()
        process.join(3)

    def test_interruption_after_reservation_resumes_by_recovery_without_resubmit(self):
        runtime=self.runtime(Provider(self.log,"interrupt"))
        runtime.start("session",self.payload)
        with self.assertRaises(SystemExit):runtime.advance("session")
        self.assertEqual(runtime._load("session").attempts[0].status,"dispatching")
        resumed=self.runtime(Provider(self.log))
        result=resumed.resume("session")
        resumed.advance("session")
        self.assertEqual(self.calls("submit"),1)
        self.assertEqual(self.calls("recover"),1)
        self.assertEqual(len(result.attempts),1)
        self.unchanged(resumed,result)

    def test_receipt_inbox_survives_interruption_before_state_application(self):
        provider=Provider(self.log,"completed")
        runtime=self.runtime(provider)
        runtime.start("session",self.payload)
        def interrupt(*args):raise SystemExit("After durable receipt inbox.")
        provider.hook=lambda request:setattr(runtime,"_drain",interrupt)
        with self.assertRaises(SystemExit):runtime.advance("session")
        self.assertEqual(len(runtime._load("session").attempts[0].receipts),0)
        resumed=self.runtime(Provider(self.log,"completed"))
        result=resumed.resume("session")
        self.assertEqual(len(result.attempts[0].receipts),1)
        self.assertEqual(result.attempts[0].completed_receipt.status,"completed")
        self.assertEqual(result.known_cost,.2)
        self.assertEqual(self.calls("submit"),1)
        self.assertEqual(self.calls("recover"),0)
        self.unchanged(resumed,result)

    def test_evaluation_inbox_is_fenced_then_replayed_without_another_evaluation(self):
        provider,evaluator=Provider(self.log,"completed"),Evaluator(self.before,self.eval_log)
        runtime=self.runtime(provider,evaluator)
        runtime.start("session",self.payload)
        runtime.advance("session")
        def interrupt(*args):raise SystemExit("After durable evaluation inbox.")
        evaluator.hook=lambda request:setattr(runtime,"_drain",interrupt)
        with self.assertRaises(SystemExit):runtime.advance("session")
        self.unchanged(runtime,runtime._load("session"))
        changed=self.runtime(Provider(self.log,"completed"),Evaluator(self.before,self.eval_log,version="changed"))
        with self.assertRaises(ValueError):changed.resume("session")
        self.unchanged(changed,changed._load("session"))
        resumed=self.runtime(Provider(self.log,"completed"),Evaluator(self.before,self.eval_log))
        result=resumed.resume("session")
        self.assertEqual(result.attempts[0].status,"accepted")
        self.assertEqual(self.eval_log.read_text().splitlines(),["evaluate"])
        self.assertEqual(self.calls("submit"),1)
        self.assertEqual(result.accepted.view_set.canonical_reference,self.before.view_set.canonical_reference)
        for item in self.before.artifacts:
            expected=glb("original untouched") if item.role=="glb" else b'{"original_source":"unchanged"}'
            self.assertEqual(resumed.store.read_artifact(item.artifact.sha256),expected)
        original_photo=next(v.image.sha256 for v in self.before.view_set.views if v.view_id=="target")
        self.assertEqual(resumed.store.read_artifact(original_photo),image(True))

    def test_late_or_cancelled_receipt_retains_usage_without_promoting(self):
        for scenario in ("late","cancel"):
            with self.subTest(scenario=scenario), temporary_directory() as folder:
                cancelled=[False]
                provider=Provider(Path(folder)/"provider.log","completed")
                runtime=LoopRuntime(Path(folder)/"store",provider=provider,clock=lambda:self.now[0])
                runtime.start("session",self.payload)
                def hook(request):
                    if scenario=="late":self.now[0]=request.expires_at+1
                    else:cancelled[0]=True
                provider.hook=hook
                state=runtime.advance("session",cancel=lambda:cancelled[0])
                self.assertEqual(state.status,"stopped" if scenario=="late" else "cancelled")
                self.assertEqual(state.known_cost,.2)
                self.assertTrue(state.attempts[0].receipts)
                self.unchanged(runtime,state)

    def test_invalid_model_parameters_usage_or_cost_never_become_a_candidate(self):
        with temporary_directory() as folder:
            valid=LoopRuntime(folder/"store",provider=Provider(folder/"provider.log","equivalent-parameters"),clock=lambda:1000.)
            valid.start("session",self.payload)
            self.assertEqual(valid.advance("session").status,"candidate_ready")
        for mode in ("invalid-model","invalid-parameters","invalid-usage-unit","cost-overrun"):
            with self.subTest(mode=mode), temporary_directory() as folder:
                provider=Provider(Path(folder)/"provider.log",mode)
                runtime=LoopRuntime(Path(folder)/"store",provider=provider,clock=lambda:1000.)
                runtime.start("session",self.payload)
                state=runtime.advance("session")
                self.assertIn(state.status,("completion_uncertain","stopped"))
                self.assertNotIn(state.attempts[0].status,("candidate_ready","evaluating","accepted"))
                self.unchanged(runtime,state)
                if mode!="cost-overrun":
                    self.assertEqual(len(state.attempts[0].rejected_receipts),1)
                    resumed=LoopRuntime(Path(folder)/"store",provider=Provider(Path(folder)/"provider.log"),clock=lambda:1000.)
                    recovered=resumed.resume("session")
                    self.assertEqual(recovered.status,"pending")
                    self.assertEqual(len(recovered.attempts[0].receipts),1)
                    self.assertEqual(len(recovered.attempts[0].rejected_receipts),1)

    def test_elapsed_budget_is_not_reset_by_restart(self):
        self.payload["budget"]=LoopBudget(max_elapsed_seconds=10.).to_dict()
        runtime=self.runtime(Provider(self.log))
        runtime.start("session",self.payload)
        self.now[0]=1011.
        resumed=self.runtime(Provider(self.log))
        state=resumed.advance("session")
        self.assertEqual(state.started_at,1000.)
        self.assertEqual(state.status,"stopped")
        self.assertIn("elapsed_budget_exhausted",state.limitations)
        self.assertEqual(self.calls("submit"),0)
        self.unchanged(resumed,state)

    def test_provisional_candidate_cannot_replace_canonical_authority(self):
        provider=Provider(self.log,"completed")
        runtime=self.runtime(provider,Evaluator(self.before,self.eval_log,canonical_change=True))
        runtime.start("session",self.payload)
        candidate_ready=runtime.advance("session")
        self.unchanged(runtime,candidate_ready)
        state=runtime.advance("session")
        self.assertFalse(state.attempts[0].decision.promoted)
        self.assertIn("canonical_authority_changed",state.attempts[0].decision.reasons)
        self.assertEqual(state.plans.view_set,self.before.view_set)
        self.unchanged(runtime,state)


if __name__=="__main__":unittest.main()
