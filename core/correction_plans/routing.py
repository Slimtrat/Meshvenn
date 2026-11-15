"""Conservative interpretation of the existing D2/D3/D4 finding vocabulary."""
from dataclasses import dataclass

from ..diagnostic_contracts import Region
from ..geometry_diagnostics.projection import check_budget
from .lineage import accepted_references


@dataclass(frozen=True)
class Route:
    report: object
    finding: object
    action: str
    target: object
    annotation: object
    reason: str


def _overlaps(a,b):
    if a.view_id!=b.view_id:
        return False
    if a.bounds is None or b.bounds is None:
        return True
    return a.bounds[0]<b.bounds[2] and b.bounds[0]<a.bounds[2] and a.bounds[1]<b.bounds[3] and b.bounds[1]<a.bounds[3]


def preparation_action(finding):
    if finding.status=="pass" or not finding.required:
        return None
    if finding.category=="input":
        if any(word in finding.code for word in ("mask","segmentation")):
            return "repair_mask"
        if finding.code=="input.subject_truncated":
            return "prepare_alignment"
        return "inspect_input"
    if finding.category=="camera":
        return "verify_camera"
    if finding.category=="alignment":
        return "select_reference" if "reference" in finding.code or "mismatch" in finding.code else "prepare_alignment"
    return None


def routes(view_set,reports,annotations,policy,report_hashes,deadline=None,cancel=None):
    views={v.view_id:v for v in view_set.views}
    all_findings=tuple(f for r in reports for f in r.findings)
    technical=any(r.completion!="complete" or any(f.required and f.category=="engine" and f.status!="pass" for f in r.findings) for r in reports)
    canonical_uncertain=any(f.code in ("appearance.canonical_reference","quality.upstream_status") and f.status!="pass" for f in all_findings)
    prepared={vid for f in all_findings if preparation_action(f) for vid in f.view_ids}
    prepared_global=any(preparation_action(f) and not f.view_ids for f in all_findings)
    local_targets={r.view_id for f in all_findings if f.code=="appearance.color_consistency" and f.status=="fail" for r in f.regions
                   if r.bounds and (r.bounds[2]-r.bounds[0])*(r.bounds[3]-r.bounds[1])<=policy.max_region_fraction}
    result=[]
    for report in reports:
        digest=report_hashes[id(report)]
        for f in report.findings:
            check_budget(deadline,cancel)
            if f.status in ("pass","not_applicable"):
                continue
            action=preparation_action(f)
            if action:
                targets=[vid for vid in f.view_ids if vid in views and views[vid].role=="observation"]
                if not targets:
                    targets=[vid for vid in f.view_ids if vid in views]
                for vid in targets or (None,):
                    target=Region(vid,"source-preparation") if vid else None
                    result.append(Route(report,f,action,target,None,"Resolve source preparation before any generative change."))
                continue
            if f.category=="engine" and f.required:
                result.append(Route(report,f,"diagnose_engine",None,None,"Technical failure or incomplete evidence requires diagnosis, not regeneration."))
                continue
            if f.category=="coverage" and f.required or f.code=="appearance.coverage":
                result.append(Route(report,f,"request_view",f.regions[0] if f.regions else None,None,
                    "Additional calibrated observation is needed; unseen surfaces are not a paint or identity fault."))
                continue
            if f.code in ("appearance.identity_assessment",) or f.code.startswith("appearance.semantic_"):
                # Model-only judgments do not acquire automatic edit authority.
                if f.required:
                    result.append(Route(report,f,"review_evidence",None,None,"Identity/model evidence needs review; no anatomical or paint change is inferred."))
                continue
            eligible=f.status=="fail" and f.code in ("appearance.color_consistency","geometry.reference_conflict","geometry.detail_preservation")
            if eligible:
                targets=[views[v] for v in f.view_ids if v in views and views[v].role=="observation"]
                candidates=[a for a in annotations if a.report_sha256==digest and a.finding_id==f.finding_id]
                regional=[(r,next((a for a in candidates if a.region==r),None)) for r in f.regions if r.view_id in views and views[r.view_id].role=="observation"]
                if candidates:
                    regional=[(a.region,a) for a in candidates]
                if not regional:
                    regional=[(None,None)]
                for region,annotation in regional:
                    check_budget(deadline,cancel)
                    if annotation is None and region is not None and any(_overlaps(region,a.region) for a in annotations):
                        # The caller's explicit edit support is a constraint, not
                        # an optional embellishment on one duplicate finding.
                        # A sibling report/component must not bypass its mask.
                        continue
                    target=views[region.view_id] if region else targets[0] if len(targets)==1 else None
                    if region and f.code=="appearance.color_consistency" and region.bounds and (
                            region.bounds[2]-region.bounds[0])*(region.bounds[3]-region.bounds[1])>policy.max_region_fraction and region.view_id in local_targets:
                        continue
                    reason=""
                    refs=accepted_references(view_set,target) if target else ()
                    if technical or canonical_uncertain or prepared_global or target and target.view_id in prepared or any(r.view_id in prepared for r in refs):
                        reason="Technical, reference or source-preparation uncertainty prevents a generative edit."
                    elif target is None or target.image is None or not refs:
                        reason="No uniquely localized observation with independent accepted design references is available."
                    elif not target.camera.verified or target.camera.projection!="orthographic":
                        reason="The original target camera is not independently verified."
                    elif region is None or region.bounds is None:
                        reason="A global score or unnamed region is not an original-image edit target."
                    else:
                        w,h=target.image.width,target.image.height
                        l,b,r,t=region.bounds
                        xs=max(0,int(r*(w-1))-int(l*(w-1))+1)
                        ys=max(0,int(t*(h-1))-int(b*(h-1))+1)
                        if xs*ys<policy.min_region_pixels or min(xs,ys)<policy.min_region_extent or (r-l)*(t-b)>policy.max_region_fraction:
                            reason="The proposed region is unresolved or too broad for a bounded local edit."
                    if not reason and f.code.startswith("geometry."):
                        same_camera=[v for v in refs if (v.camera.projection,v.camera.azimuth_degrees,v.camera.elevation_degrees,v.camera.flip_x)==
                                     (target.camera.projection,target.camera.azimuth_degrees,target.camera.elevation_degrees,target.camera.flip_x)]
                        anchored=any(g.code=="geometry.reference_conflict" and g.status=="fail" and target.view_id in g.view_ids and
                            any(v.view_id in g.view_ids and (v.camera.projection,v.camera.azimuth_degrees,v.camera.elevation_degrees,v.camera.flip_x)==
                                (target.camera.projection,target.camera.azimuth_degrees,target.camera.elevation_degrees,target.camera.flip_x)
                                for v in refs) for g in report.findings)
                        if not anchored or annotation is None:
                            reason="Geometric residuals do not identify source truth or their original-image frame; an explicit source annotation and canonical attribution are required."
                        elif len({(v.image.sha256,v.mask.sha256 if v.mask else None) for v in same_camera})>1:
                            reason="Several accepted same-camera sources have not been jointly arbitrated; select an explicit canonical authority before editing."
                    if not reason and f.code.startswith("appearance."):
                        qualified=any(e.code=="appearance.coverage" and e.status=="pass" and region in e.regions for e in report.findings)
                        unresolved=any(g.code in ("appearance.coverage","appearance.lighting_variation") and g.required and g.status!="pass" and
                            (not g.regions and target.view_id in g.view_ids or any(_overlaps(region,r) for r in g.regions)) for g in all_findings)
                        if not qualified or unresolved:
                            reason="This original-image region lacks resolved visible calibrated support."
                    if not reason and any(g.code==f.code and g.status!=f.status and g.regions==f.regions and
                            g.view_ids==f.view_ids for other in reports if other is not report for g in other.findings):
                        reason="Current diagnostic snapshots disagree on this exact check and region; select the authoritative evidence instead of editing arbitrarily."
                    result.append(Route(report,f,"select_reference" if reason else "edit_region",region,annotation,
                        reason or "A localized measured contradiction supports a candidate edit relative to the accepted design, not a diagnosis of physical truth."))
                continue
            if f.category=="geometry" and f.required or f.code=="appearance.canonical_reference":
                result.append(Route(report,f,"select_reference",f.regions[0] if f.regions else None,None,
                    "Measured contradictions identify a suspect group, not which view is physically true; choose an authoritative reference."))
            elif f.required:
                result.append(Route(report,f,"review_evidence",f.regions[0] if f.regions else None,None,
                    "Required evidence remains unresolved; inspect this diagnostic before choosing any image-content change."))
    return result
