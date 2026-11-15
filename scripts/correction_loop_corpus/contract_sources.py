"""Explicit simulated evaluator reports for orchestration, never quality evidence."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from core.correction_plans import (CorrectionPolicy,EditAnnotation,ProviderCapabilities,
                                   plan_corrections,prepare_correction)
from core.diagnostic_contracts import (ArtifactReference,CameraDeclaration,CanonicalReference,
    DiagnosticPolicy,DiagnosticReport,DiagnosticResolution,EngineVersion,Evidence,Finding,
    Measurement,Region,ViewRevision,ViewSetRevision)
from core.geometry_diagnostics.models import MaskArtifact
from core.image_mask import BinaryMask
from core.diagnostics_preflight import RasterInput
from scripts.appearance_diagnostic_corpus.authoring import sha256

ENGINE=EngineVersion("corpus.simulated_global_evaluator","1")
REGION=Region("target","authored-colour-patch",(.30,.25,.60,.50))
CHECKS=("appearance.identity_assessment","quality.export_verified","correction.healthy_constraints",
        "correction.camera_compliance","geometry.important_part")


def capabilities():
    return ProviderCapabilities("corpus.provider_simulator","1",("region_edit","mask","multiple_references",
                                "camera_request","identity_reference"),8)


def report_for(view_set,proof,outcome="baseline",*,export_artifact=None):
    """Statuses/metrics here are contract data, not results of NativeCore/models."""
    identity="unknown" if outcome in ("baseline","required_unknown") else "fail" if outcome=="identity_failure" else "pass"
    part="fail" if outcome=="higher_mean_part_failure" else "pass"
    colour="fail" if outcome in ("baseline","no_progress") else "pass"
    values=(("appearance.color_consistency",colour,"appearance",(REGION,)),
            ("appearance.coverage","pass","coverage",(REGION,)),
            ("appearance.canonical_reference","pass","appearance",()),
            ("appearance.identity_assessment",identity,"appearance",()),
            ("geometry.important_part",part,"geometry",()),
            ("quality.export_verified","pass","quality",()),
            ("correction.healthy_constraints","pass","quality",()),
            ("correction.camera_compliance","pass","camera",()))
    findings=[]
    for index,(code,status,category,regions) in enumerate(values):
        observation=Evidence("contract-e-"+str(index),"execution",
            "Local simulated evaluator contract; this is not measured asset/model/provider fidelity.",
            ("target",),regions,(Measurement("contract_check_satisfied",float(status=="pass"),"contract_boolean"),),
            export_artifact if code=="quality.export_verified" and export_artifact is not None else proof)
        findings.append(Finding("contract-f-"+str(index),code,category,"error" if status=="fail" else "info",status,
            "Simulated global check for conditional loop-orchestration qualification.",("target",),regions,(observation,),
            reason="Synthetic evaluator contract leaves this required check unknown." if status=="unknown" else ""))
    policy=DiagnosticPolicy("corpus.simulated_global_policy","1",sha256(b"D6-contract-evaluator-v1"),
                            tuple(code for code,_,_,_ in values))
    return DiagnosticReport("contract-report-"+str(view_set.revision),view_set,(ENGINE,),policy,
        DiagnosticResolution(32,32),tuple(findings),
        assumptions=("Simulation only: no semantic model, NativeCore fidelity or real GLB delivery is qualified.",))


def initialize_contract_source(root):
    from core.correction_loop.models import AcceptancePolicy,LoopSnapshot,SnapshotArtifact
    proof=ArtifactReference("original-D6-authoring",sha256((root/"original-source.json").read_bytes()),
                            "application/json","original-source.json")
    camera=CameraDeclaration("orthographic",0.,0.,False,True,proof)
    photo=RasterInput.from_path(root/"assets/original-photo.png")
    reference=RasterInput.from_path(root/"assets/accepted-reference.png")
    target=ViewRevision("target",1,photo.content_reference(),None,camera,origin="user",
                        origin_details="Original analytic user-origin stand-in, not a real photograph.")
    ref=ViewRevision("reference",1,reference.content_reference(),None,camera,role="reference",origin="rendered")
    canonical=CanonicalReference("original-D6-design",1,ref.image,True,(ref.view_id,),proof)
    view_set=ViewSetRevision("D6-contract-source",1,(target,ref),canonical)
    glb_data=(root/"assets/original.glb").read_bytes()
    glb=ArtifactReference("original-glb",sha256(glb_data),"model/gltf-binary")
    report=report_for(view_set,proof,export_artifact=glb)
    support=bytes(int(11<=x<16 and 9<=y<14) for y in range(32) for x in range(32))
    annotation=EditAnnotation(sha256(report.to_json().encode()),"contract-f-0",REGION,proof,
                              MaskArtifact.from_mask(BinaryMask(32,32,support)))
    policy=CorrectionPolicy()
    planned=plan_corrections(view_set,(report,),capabilities=capabilities(),annotations=(annotation,),policy=policy)
    plan=next(p for p in planned.plans if p.action_kind=="edit_region" and p.readiness=="ready")
    prepared=prepare_correction(plan,view_set,(report,),capabilities=capabilities(),annotations=(annotation,),policy=policy)
    snapshot=LoopSnapshot("contract-initial",view_set,(report,),
        (Measurement("target_error",.2,"normalized_error"),Measurement("mean_iou",.8,"ratio")),
        (SnapshotArtifact("glb",glb),
         SnapshotArtifact("source_state",proof)))
    acceptance=AcceptancePolicy(required_checks=CHECKS,required_engines=(ENGINE.engine_id,))
    return {"accepted":snapshot,"proof":proof,"annotations":(annotation,),"policy":policy,
            "planned":planned,"prepared":prepared,"acceptance_policy":acceptance,
            "artifacts":{target.image.sha256:(root/"assets/original-photo.png").read_bytes(),
                         ref.image.sha256:(root/"assets/accepted-reference.png").read_bytes(),
                         proof.sha256:(root/"original-source.json").read_bytes(),sha256(glb_data):glb_data}}


def simulated_candidate(context,request,image_ref,root,outcome):
    from core.correction_loop.models import LoopSnapshot,SnapshotArtifact
    original=context["accepted"].view_set
    target=next(v for v in original.views if v.view_id=="target")
    image=RasterInput.from_path(root/("assets/candidate-erased-part.png" if outcome=="higher_mean_part_failure" else
                                    "assets/candidate-improved.png"))
    if image.source_sha256!=image_ref.sha256:
        raise ValueError("Simulated evaluator input differs from actual provider output")
    candidate=replace(target,revision=target.revision+request.attempt_number,image=image.content_reference(),origin="derived",
                      derived_from=tuple(request.prepared.derived_from),origin_details="Local simulated candidate; no provider fidelity claim.")
    view_set=replace(original,revision=original.revision+request.attempt_number,
                     views=tuple(candidate if v.view_id=="target" else v for v in original.views))
    mean=.98 if outcome=="higher_mean_part_failure" else .8 if outcome=="no_progress" else .95
    error=1-mean
    glb_data=(root/"assets/candidate.glb").read_bytes()
    glb=ArtifactReference("candidate-glb",sha256(glb_data),"model/gltf-binary")
    extra=(SnapshotArtifact("mesh",glb),) if context.get("include_provisional_mesh") else ()
    snapshot=LoopSnapshot("contract-candidate-"+str(request.attempt_number),view_set,
        (report_for(view_set,context["proof"],outcome,export_artifact=glb),),
        (Measurement("target_error",error,"normalized_error"),Measurement("mean_iou",mean,"ratio")),
        (SnapshotArtifact("glb",glb),SnapshotArtifact("source_state",context["proof"]))+extra)
    return snapshot,((glb.sha256,glb_data),)
