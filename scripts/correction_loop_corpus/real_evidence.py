"""Real D2/D4 integration behind the local evaluator port, without identity claims."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from core.appearance_diagnostics import (AppearancePolicy, AppearanceRegionAnchor, analyze_appearance)
from core.correction_plans import CorrectionPolicy, plan_corrections, prepare_correction
from core.diagnostic_contracts import ArtifactReference, Region
from core.diagnostics_preflight import (AlignmentAnchor, PreflightPolicy, RasterInput, ViewInput,
                                      analyze_preflight)
from scripts.appearance_diagnostic_corpus.authoring import png_rgba, sha256
from scripts.appearance_diagnostic_corpus.fixtures import REGIONS
from scripts.appearance_diagnostic_corpus.integrity import load_manifest as load_appearance
from scripts.correction_plan_corpus.integrity import load_manifest as load_plans
from scripts.correction_plan_corpus.runner import annotations_for, capabilities_for
from scripts.correction_plan_corpus.sources import execute_source

ROOT=Path(__file__).resolve().parents[2]


def initialize_real_source():
    corpus=ROOT/"tests/fixtures/diagnostics/correction-plan-v1"
    manifest,_=load_plans(corpus)
    case=next(c for c in manifest["cases"] if c["case_id"]=="targeted_visible_colour")
    context=execute_source(corpus,case)
    policy=CorrectionPolicy()
    capabilities=capabilities_for(case)
    annotations=annotations_for(context)
    planned=plan_corrections(context["view_set"],context["reports"],capabilities=capabilities,
                             annotations=annotations,policy=policy)
    plan=next(p for p in planned.plans if p.action_kind=="edit_region" and p.readiness=="ready")
    prepared=prepare_correction(plan,context["view_set"],context["reports"],capabilities=capabilities,
                                 annotations=annotations,policy=policy)
    reference=context["inputs"]["reference"].image
    rgba=bytes(max(0,min(255,round(value*255))) for value in reference.rgba)
    candidate=png_rgba(reference.width,reference.height,rgba,author_tag="original-D6-controlled-accepted-design-candidate")
    context.update(prepared=prepared,planned=planned,candidate_png=candidate)
    return context


def evaluate_real_candidate(context,*,derived_from=None):
    """Called only by the evaluator adapter after the simulated provider reply."""
    original=context["view_set"]
    image=RasterInput.from_png_bytes(context["candidate_png"])
    target=next(v for v in original.views if v.view_id=="target")
    proof=ArtifactReference("D6-controlled-render-proof",sha256(context["candidate_png"]),"image/png")
    candidate=replace(target,revision=target.revision+1,image=image.content_reference(),origin="derived",
                      derived_from=tuple(derived_from) if derived_from is not None else (target.image.sha256,),
                      origin_details="Original analytic controlled candidate; not an actual provider photograph.")
    view_set=replace(original,revision=original.revision+1,
                     views=tuple(candidate if v.view_id=="target" else v for v in original.views))
    inputs={**context["inputs"],"target":ViewInput(image)}
    preflight=analyze_preflight(view_set,inputs,
        anchors=(AlignmentAnchor("target","reference",original.canonical_reference.validation_evidence.sha256),),
        policy=PreflightPolicy(required_cameras=((0.,0.),)))
    parent_root=ROOT/"tests/fixtures/diagnostics/appearance-v1"
    parent,_=load_appearance(parent_root)
    case=next(c for c in parent["cases"] if c["case_id"]=="local_colour_change")
    bounds=case["surface_region"]
    regions=[]
    anchors=[]
    baseline=context["upstream_result"]
    for view in baseline.views:
        for result in view.regions:
            if result.region.label not in ("colour_patch","unaffected_shared_region"):
                continue
            region=result.region
            regions.append(region)
            source=bounds if region.label=="colour_patch" else REGIONS["shared_patch"]
            anchors.append(AppearanceRegionAnchor(region,(source["x"][0],source["y"],source["z"][0]),
                (source["x"][1],source["y"],source["z"][1]),proof,(0,1)))
    settings={v.view_id:v.settings for v in baseline.views}
    appearance=analyze_appearance(view_set,inputs,surface=baseline.surface,view_settings=settings,
        regions=tuple(regions),region_anchors=tuple(anchors),policy=AppearancePolicy(sampling_size=32,max_seconds=20.))
    before=[r for v in baseline.views for r in v.regions if r.region.view_id=="target" and r.region.label=="colour_patch"]
    after=[r for v in appearance.views for r in v.regions if r.region.view_id=="target" and r.region.label=="colour_patch"]
    return {"view_set":view_set,"inputs":inputs,"reports":(preflight.report,appearance.report),
            "appearance":appearance,"preflight":preflight,"baseline_regions":before,"candidate_regions":after,
            "identity_status":appearance.identity_status,
            "numeric_improved":bool(before and after) and all(r.color_status=="fail" and r.changed_samples>0 for r in before) and
                               all(r.color_status=="pass" and r.changed_samples==0 for r in after),
            "GLB_quality":"unknown; the separate triangle rollback asset is not the appearance surface",
            "provider_fidelity_qualified":False}


def initialize_real_loop_source(root):
    from core.correction_loop.models import AcceptancePolicy,LoopSnapshot,SnapshotArtifact
    from core.diagnostic_contracts import Measurement
    source=initialize_real_source()
    glb_data=(root/"assets/original.glb").read_bytes()
    source_data=source["original_authoring_path"].read_bytes()
    glb=ArtifactReference("real-control-original-glb",sha256(glb_data),"model/gltf-binary")
    original=ArtifactReference("real-control-original-source",sha256(source_data),"application/json")
    before=[r for v in source["upstream_result"].views for r in v.regions if r.region.view_id=="target" and r.region.label=="colour_patch"]
    error=sum(r.changed_samples for r in before)/max(1,sum(r.comparable_samples for r in before))
    artifacts=tuple((SnapshotArtifact("glb",glb),SnapshotArtifact("source_state",original)))
    accepted=LoopSnapshot("real-D2-D4-initial",source["view_set"],source["reports"],
                          (Measurement("target_error",error,"normalized_error"),),artifacts)
    data={sha256(glb_data):glb_data,sha256(source_data):source_data}
    for roles in source["asset_paths"].values():
        for path in roles.values():
            payload=path.read_bytes();data[sha256(payload)]=payload
    def snapshot_factory(result,request):
        changed=sum(r.changed_samples for r in result["candidate_regions"])
        total=sum(r.comparable_samples for r in result["candidate_regions"])
        return LoopSnapshot("real-D2-D4-candidate-"+str(request.attempt_number),result["view_set"],result["reports"],
                            (Measurement("target_error",changed/max(1,total),"normalized_error"),),artifacts)
    return {"accepted":accepted,"annotations":source["planned"].annotations,"policy":source["planned"].policy,
            "prepared":source["prepared"],"planned":source["planned"],"artifacts":data,
            "acceptance_policy":AcceptancePolicy(),"real_snapshot_factory":snapshot_factory,
            "original_files":{"photo":source["asset_paths"]["target"]["image"],
                              "source":source["original_authoring_path"],"glb":root/"assets/original.glb"}},source
