"""Pure offline planning and exact-context provider package preparation."""
from __future__ import annotations

import hashlib
import time
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from ..diagnostic_contracts import EngineVersion, Judgment
from ..diagnostic_contracts.codec import fingerprint
from ..geometry_diagnostics.projection import check_budget
from .lineage import accepted_references
from .models import (CorrectionPlan,CorrectionResult,PlanEvidence,PreparedCorrection,
                     ProviderCapabilities)
from .packages import camera_requirement,make_package
from .policy import CorrectionPolicy
from .routing import Route,routes

ENGINE=EngineVersion("meshvenn.correction_plans","1.0.0")


@lru_cache(maxsize=1)
def _source_hash():
    directory=Path(__file__).resolve().parent
    root=directory.parent
    paths=[*directory.glob("*.py"),*(root/"diagnostic_contracts").glob("*.py"),
           root/"geometry_diagnostics/models.py",root/"geometry_diagnostics/projection.py",
           root/"projection_alignment.py",root/"image_mask.py"]
    digest=hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode()+b"\0"+path.read_bytes())
    return digest.hexdigest()


def _inputs(view_set,reports,capabilities,annotations,policy,deadline,cancel):
    reports,annotations=tuple(reports),tuple(annotations)
    if len(view_set.views)>20 or len(reports)>20 or len(annotations)>policy.max_annotations:
        raise ValueError("Correction planning input counts exceed their bounds.")
    if sum(len(r.findings) for r in reports)>policy.max_findings:
        raise ValueError("Correction finding budget exceeded.")
    if sum(len(f.regions) for r in reports for f in r.findings)>policy.max_findings:
        raise ValueError("Correction region evidence budget exceeded.")
    hashes={}
    for report in reports:
        check_budget(deadline,cancel)
        hashes[id(report)]=fingerprint(report.to_dict())
        check_budget(deadline,cancel)
    if len(set(hashes.values()))!=len(reports):
        raise ValueError("Duplicate report snapshots are not extra evidence.")
    reports=tuple(sorted(reports,key=lambda r:hashes[id(r)]))
    views={view.view_id:view for view in view_set.views}
    keys=set()
    for annotation in annotations:
        check_budget(deadline,cancel)
        key=(annotation.report_sha256,annotation.finding_id,annotation.region.view_id)
        if key in keys:
            raise ValueError("Duplicate/competing source annotations require a reference decision.")
        keys.add(key)
        report=next((r for r in reports if hashes[id(r)]==annotation.report_sha256),None)
        finding=next((f for f in report.findings if f.finding_id==annotation.finding_id),None) if report else None
        if finding is None or annotation.region.view_id not in views or annotation.region.view_id not in (
                set(finding.view_ids)|{r.view_id for r in finding.regions}):
            raise ValueError("Annotation does not belong to the exact report, finding and source view.")
        image=views[annotation.region.view_id].image
        if image is None:
            raise ValueError("A source annotation requires its original image reference.")
        if annotation.mask is not None:
            mask=annotation.mask
            if mask.width>image.width or mask.height>image.height or abs(mask.width*image.height-mask.height*image.width)>max(image.width,image.height):
                raise ValueError("An edit mask must preserve original full-frame aspect without upsampling.")
        if finding.code.startswith("appearance.") and finding.regions:
            l,b,r,t=annotation.region.bounds
            if not any(region.view_id==annotation.region.view_id and region.bounds and
                       region.bounds[0]<=l<r<=region.bounds[2] and region.bounds[1]<=b<t<=region.bounds[3]
                       for region in finding.regions):
                raise ValueError("An annotation cannot move an observed appearance fault to another source region.")
    annotations=tuple(sorted(annotations,key=lambda a:(a.report_sha256,a.finding_id,a.region.view_id)))
    context=fingerprint({"view_set":view_set.dependency_dict(),"reports":sorted(hashes.values()),
        "capabilities":capabilities.to_dict(),"annotations":[a.to_dict() for a in annotations],
        "policy":policy.dependency_fingerprint,"engine":ENGINE.to_dict(),"source":_source_hash()})
    check_budget(deadline,cancel)
    return reports,annotations,hashes,context


def _evidence(report,finding,hashes):
    return PlanEvidence(hashes[id(report)],finding.finding_id,finding.code,finding.status.value,finding.evidence)


def _plan(view_set,reports,route,hashes,context,capabilities):
    evidence=[_evidence(route.report,route.finding,hashes)]
    if route.action=="edit_region" or route.finding.code.startswith("geometry."):
        for report in reports:
            for finding in report.findings:
                if finding.code in ("appearance.coverage","geometry.reference_conflict") and finding.status in ("pass","fail") and (
                        route.target is not None and (route.target in finding.regions or route.target.view_id in finding.view_ids and finding.code=="geometry.reference_conflict")):
                    item=_evidence(report,finding,hashes)
                    if item not in evidence:
                        evidence.append(item)
    target=next((v for v in view_set.views if route.target and v.view_id==route.target.view_id),None)
    references=accepted_references(view_set,target)
    camera=camera_requirement(view_set,route.target,route.action,route.finding)
    controls=[]
    if route.action=="edit_region":
        controls=["region_edit","camera_request","identity_reference"]
        if len(references)>1:
            controls.append("multiple_references")
        if route.annotation and route.annotation.mask:
            controls.append("mask")
    missing=tuple(sorted(set(controls)-set(capabilities.controls)))
    limitations=[route.reason,"Plans propose a candidate; they certify neither identity nor provider compliance nor delivered GLB quality."]
    if len(references)>capabilities.max_references and route.action=="edit_region":
        missing=tuple(sorted(set(missing)|{"multiple_references"}))
        limitations.append("The accepted reference set exceeds the provider's reference budget; references were not silently discarded.")
    readiness="unsupported" if missing else "ready" if route.action=="edit_region" else "needs_input"
    if readiness=="unsupported":
        limitations.append("Unsupported requested controls: "+", ".join(missing)+". No control was silently dropped.")
    alternative=("Choose an adapter supporting all requested controls, or manually review/edit the named region using the same references and postconditions."
                 if readiness=="unsupported" else "Resolve the attached preparation/reference/evidence request before a generative edit."
                 if readiness=="needs_input" else "A human may perform the same bounded edit and submit the result to the same global postchecks.")
    package=make_package(view_set,reports,route,tuple(evidence),references,camera)
    identifier=fingerprint({"context":context,"action":route.action,"target":route.target.to_dict() if route.target else None,
        "evidence":[e.to_dict() for e in evidence],"annotation":route.annotation.to_dict() if route.annotation else None})[:28]
    return CorrectionPlan("correction-"+identifier,context,route.action,readiness,route.target,tuple(evidence),
        Judgment(route.reason,"inference","This is a conditional interpretation of declared evidence. A selected canonical design is an authority choice, not physical truth."),
        "Resolve the named measured contradiction without changing protected evidence or creating any new global failure.",
        tuple(sorted(controls)),missing,tuple(limitations),alternative,package)


def plan_corrections(view_set,reports,*,capabilities=None,annotations=(),policy=None,cancel=None):
    """Build bounded inspectable plans, without a provider, network or image edits."""
    policy=policy or CorrectionPolicy()
    capabilities=capabilities or ProviderCapabilities()
    deadline=time.monotonic()+policy.max_seconds
    reports,annotations=tuple(reports),tuple(annotations)
    # Counts remain checked even on an immediately cancelled request. A typed
    # incomplete result carries unprocessed snapshots but never executable plans.
    if len(view_set.views)>20 or len(reports)>20 or len(annotations)>policy.max_annotations:
        raise ValueError("Correction input counts exceed their bounds.")
    try:
        check_budget(deadline,cancel)
        reports,annotations,hashes,context=_inputs(view_set,reports,capabilities,annotations,policy,deadline,cancel)
    except (InterruptedError,TimeoutError) as exc:
        context=fingerprint({"incomplete_input_processing":True,"view_set":view_set.dependency_fingerprint,
            "report_count":len(reports),"policy":policy.dependency_fingerprint,"capabilities":capabilities.dependency_fingerprint})
        return CorrectionResult(view_set,reports,capabilities,annotations,policy.dependency_fingerprint,ENGINE,
            _source_hash(),context,(),"cancelled" if isinstance(exc,InterruptedError) else "partial",
            limitations=("Input processing ended before complete context binding; no plan was authorized.",),policy=policy)
    plans=[]
    completion="complete"
    stale=any(report.view_set.dependency_fingerprint!=view_set.dependency_fingerprint for report in reports)
    try:
        check_budget(deadline,cancel)
        if stale:
            # Stale input evidence cannot acquire current authority even if its
            # finding names happen to match this revision.
            report=next(r for r in reports if r.view_set.dependency_fingerprint!=view_set.dependency_fingerprint)
            finding=report.findings[0] if report.findings else None
            if finding:
                route=Route(report,finding,"review_evidence",None,None,"The diagnostic report belongs to a different source revision; rerun it before planning an edit.")
                p=_plan(view_set,reports,route,hashes,context,capabilities)
                plans.append(replace(p,readiness="blocked"))
            completion="partial"
        else:
            candidates=routes(view_set,reports,annotations,policy,hashes,deadline,cancel)
            # Preparations precede technical/ref choices and only then edits.
            priority={"prepare_alignment":0,"repair_mask":0,"inspect_input":0,"verify_camera":0,
                      "diagnose_engine":1,"select_reference":2,"request_view":3,"review_evidence":4,"edit_region":5}
            candidates.sort(key=lambda r:(priority[r.action],hashes[id(r.report)],r.finding.finding_id,
                r.target.view_id if r.target else "",r.target.bounds if r.target and r.target.bounds else ()))
            unique=set()
            for route in candidates:
                check_budget(deadline,cancel)
                plan=_plan(view_set,reports,route,hashes,context,capabilities)
                if plan.plan_id in unique:
                    continue
                if len(plans)>=policy.max_plans:
                    completion="partial"
                    break
                unique.add(plan.plan_id)
                plans.append(plan)
            if any(report.completion!="complete" for report in reports):
                completion="partial"
        check_budget(deadline,cancel)
    except InterruptedError:
        completion="cancelled"
    except TimeoutError:
        completion="partial"
    return CorrectionResult(view_set,reports,capabilities,annotations,policy.dependency_fingerprint,ENGINE,
        _source_hash(),context,tuple(plans),completion,policy=policy)


def prepare_correction(plan,view_set,reports,*,capabilities=None,annotations=(),policy=None):
    """Recompute exact authority and return a candidate-only request, not an edit.

    Neither a copied context hash nor a modified JSON plan is execution
    authorization. Reusing a plan requires unchanged current evidence, policy,
    provider capabilities, annotation, accepted reference and implementation.
    """
    result=plan_corrections(view_set,reports,capabilities=capabilities,annotations=annotations,policy=policy)
    if result.completion!="complete" or plan.context_sha256!=result.context_sha256:
        raise ValueError("Correction plan is stale, incomplete or belongs to a different context.")
    expected=next((p for p in result.plans if p.plan_id==plan.plan_id),None)
    if expected is None or expected!=plan:
        raise ValueError("Correction plan was modified or does not match the freshly planned evidence.")
    if plan.action_kind!="edit_region" or plan.readiness!="ready":
        raise ValueError("Manual, ambiguous or unsupported plans cannot be prepared as provider edits.")
    sources=(plan.prompt.original,*plan.prompt.references)
    derived=tuple(sorted({content.sha256 for view in sources if view for content in (view.image,view.mask) if content}))
    return PreparedCorrection(plan.plan_id,plan.context_sha256,plan.prompt,derived,plan.prompt.postconditions)
