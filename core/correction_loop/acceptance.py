"""No mean-score vote can overrule missing parts, identity or global evidence."""
from .models import AcceptanceDecision


def assess(before,request,evaluation,policy,*,protected_pixels):
    candidate=evaluation.candidate
    reasons=[]
    required_status="pass"
    if evaluation.request_id!=request.request_id or evaluation.request_sha256!=request.sha256:
        reasons.append("evaluation_request_mismatch")
    a,b=before.view_set,candidate.view_set
    target=request.plan.target.view_id
    originals={v.view_id:v for v in a.views}
    revised={v.view_id:v for v in b.views}
    if a.view_set_id!=b.view_set_id or b.revision<=a.revision or set(originals)!=set(revised):
        reasons.append("view_set_not_complete_or_new")
    if a.canonical_reference!=b.canonical_reference:
        reasons.append("canonical_authority_changed")
    if set(evaluation.checked_view_ids)!=set(originals):
        reasons.append("global_views_not_evaluated")
    for vid,old in originals.items():
        new=revised.get(vid)
        if new is None: continue
        if vid!=target and new!=old:
            reasons.append("healthy_or_reference_view_changed:"+vid)
        if vid==target:
            if new.image is None or old.image is None or (new.image.width,new.image.height)!=(old.image.width,old.image.height):
                reasons.append("candidate_image_grid_changed")
            if new.camera!=old.camera or new.alignment!=old.alignment:
                reasons.append("camera_or_alignment_changed")
            if new.revision<=old.revision or new.origin!="derived" or not set(request.prepared.derived_from)<=set(new.derived_from):
                reasons.append("candidate_lineage_invalid")
    if protected_pixels is None:reasons.append("protected_pixels_unresolved");required_status="unknown"
    elif not protected_pixels:reasons.append("protected_pixels_changed");required_status="fail"
    if not candidate.reports: reasons.append("global_reports_missing");required_status="unknown"
    engines={e.engine_id for r in candidate.reports for e in r.engines}
    for engine in policy.required_engines:
        if engine not in engines: reasons.append("required_engine_missing:"+engine);required_status="unknown"
    findings=[f for r in candidate.reports for f in r.findings]
    for report in candidate.reports:
        if report.completion!="complete" or report.missing_required_checks:
            reasons.append("incomplete_global_report:"+report.report_id)
            if required_status!="fail":required_status="unknown"
        codes=set(report.policy.required_checks)
        for finding in report.findings:
            if finding.required or finding.code in codes or finding.severity=="blocking":
                if finding.status!="pass":
                    reasons.append("required_"+finding.status.value+":"+finding.code)
                    if finding.status=="fail": required_status="fail"
                    elif required_status!="fail": required_status="unknown"
    for code in policy.required_checks:
        matches=[f for f in findings if f.code==code]
        if not matches or any(f.status!="pass" for f in matches):
            reasons.append("profile_check_unresolved:"+code)
            if any(f.status=="fail" for f in matches):required_status="fail"
            elif required_status!="fail":required_status="unknown"
    for region in policy.required_regions:
        matches=[f for f in findings if region in f.regions]
        if not matches or any(f.status!="pass" for f in matches):
            reasons.append("required_region_unresolved:"+region.view_id+":"+region.label)
            if any(f.status=="fail" for f in matches):required_status="fail"
            elif required_status!="fail":required_status="unknown"
    if "quality.export_verified" in policy.required_checks:
        glbs={a.artifact.sha256 for a in candidate.artifacts if a.role=="glb"}
        verified={e.artifact.sha256 for f in findings if f.code=="quality.export_verified" and f.status=="pass"
                  for e in f.evidence if e.artifact is not None}
        if not glbs or not glbs<=verified:
            reasons.append("exact_export_artifact_evidence_missing")
            if required_status!="fail":required_status="unknown"
    if {a.role for a in before.artifacts}-{a.role for a in candidate.artifacts}:
        reasons.append("delivery_artifact_role_lost")
    def objective(snapshot):
        return next((m.value for m in snapshot.metrics if m.name==policy.objective_name and m.unit==policy.objective_unit),None)
    old,new=objective(before),objective(candidate)
    improvement=None if old is None or new is None else old-new if policy.objective_direction=="lower" else new-old
    if improvement is None:
        reasons.append("comparable_objective_missing")
        if required_status!="fail":required_status="unknown"
    elif improvement<policy.min_improvement: reasons.append("no_measured_improvement")
    reasons=tuple(dict.fromkeys(reasons))
    hard=("evaluation_request_mismatch","view_set_not_complete_or_new","canonical_authority_changed",
          "candidate_image_grid_changed","camera_or_alignment_changed","candidate_lineage_invalid",
          "protected_pixels_changed","delivery_artifact_role_lost")
    if any(r in hard or r.startswith("healthy_or_reference_view_changed:") for r in reasons):required_status="fail"
    return AcceptanceDecision(not reasons,reasons,improvement,required_status,before.sha256,candidate.sha256)
