"""Bounded D4 composition: measured color, visibility and optional judgments.

The declared normalized mesh supplies correspondence, not ground truth. Missing
coverage is unknown; fitted exposure is an observation, never a calibration.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

from ..diagnostic_contracts import (ArtifactReference, DiagnosticReport, DiagnosticResolution,
    EngineVersion, Evidence, Finding, Measurement, Region)
from ..diagnostic_contracts.codec import fingerprint
from ..diagnostics_preflight import analyze_preflight
from ..diagnostics_preflight.registration import mask_from_input
from ..geometry_diagnostics.projection import check_budget
from .comparison import aggregate_view, canonical_conflicts, compare_pair
from .correspondence import SurfaceSampler
from .models import AppearanceProvenance, AppearanceResult
from .policy import AppearancePolicy, AppearanceViewSettings
from .semantic_models import SemanticRegionPair, SemanticRequest, make_semantic_image
from .semantics import analyze_semantics

ENGINE = EngineVersion("meshvenn.appearance_diagnostics", "1.0.0")


@lru_cache(maxsize=1)
def _source_hash():
    root = Path(__file__).resolve().parent.parent
    paths = [path for directory in ("appearance_diagnostics", "diagnostic_contracts",
             "diagnostics_preflight", "projection_math", "material_visibility", "geometry_diagnostics")
             for path in (root/directory).glob("*.py") if path.name != "blender_backend.py"]
    paths += [root/name for name in ("projection_alignment.py", "image_mask.py")]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode()+b"\0"+path.read_bytes())
    return digest.hexdigest()


def _grid(data, size):
    w,h = data.image.width,data.image.height
    factor = min(1.,size/max(w,h))
    return max(1,round(w*factor)),max(1,round(h*factor))


def _lineage(reference, target, views):
    """Canonical ancestors are allowed; reference descendants/cycles are not."""
    graph = {}
    for view in views:
        for content in (view.image,view.mask):
            if content is not None:
                graph.setdefault(content.sha256,set()).update(view.derived_from)
    target_hashes = {source.sha256 for source in (target.image,target.mask) if source}
    active,done = set(),set()
    def visit(digest):
        if digest in active:
            return "circular"
        if digest in done:
            return "accepted"
        if digest in target_hashes:
            return "target_derived"
        active.add(digest)
        for parent in graph.get(digest,()):
            result = visit(parent)
            if result != "accepted":
                return result
        active.remove(digest)
        done.add(digest)
        return "accepted"
    # Equal immutable image bytes are a valid unchanged comparison, unless the
    # producer explicitly declared a derivation edge to the target.
    for digest in reference.derived_from:
        result = visit(digest)
        if result != "accepted":
            return result
    return "accepted"


def _snapshots(view_set, inputs, settings, valid, decoded, deadline, cancel):
    images = []
    for view in view_set.views:
        check_budget(deadline,cancel)
        if view.view_id not in valid or settings[view.view_id].color_space == "unknown":
            continue
        image = inputs[view.view_id].image
        width,height = _grid(inputs[view.view_id],128)
        rgba = []
        for y in range(height):
            sy = round((y/(height-1) if height>1 else .5)*(image.height-1))
            for x in range(width):
                sx = round((x/(width-1) if width>1 else .5)*(image.width-1))
                offset = 4*(sy*image.width+sx)
                rgba.extend(image.rgba[offset:offset+4])
        images.append(make_semantic_image(view_id=view.view_id,source=view.image,
            original_decoded_sha256=decoded[view.view_id],source_width=image.width,source_height=image.height,
            width=width,height=height,rgba=rgba,color_space=settings[view.view_id].color_space))
    return tuple(images)


def _semantic_pairs(pairs, views, images, context, max_pairs):
    """Regions bound to actual corresponding original pixels, not mirrored ROIs."""
    images = {image.view_id:image for image in images}
    results = []
    for pair in pairs:
        if pair.map_view_id != pair.target_view_id or pair.target_view_id not in images or pair.reference_view_id not in images:
            continue
        target = next(v for v in views if v.view_id == pair.target_view_id)
        reference = next(v for v in views if v.view_id == pair.reference_view_id)
        samples = [p for p in pair.pixels if p.visibility == "visible" and p.target_uv is not None and p.reference_uv is not None]
        def bounds(points):
            if not points:
                return None
            # A single subpixel correspondence must never become a full image.
            lo = [min(p[i] for p in points) for i in (0,1)]
            hi = [max(p[i] for p in points) for i in (0,1)]
            return tuple((lo[0],lo[1],hi[0],hi[1])) if all(a<b for a,b in zip(lo,hi)) else None
        target_bounds = bounds([p.target_uv for p in samples])
        reference_bounds = bounds([p.reference_uv for p in samples])
        complete = (len(samples) == sum(pair.expected_mask.values) and
                    target_bounds is not None and reference_bounds is not None)
        results.append(SemanticRegionPair("semantic-"+pair.pair_id,
            Region(pair.target_view_id,"visible-correspondence",target_bounds),
            Region(pair.reference_view_id,"visible-correspondence",reference_bounds),
            images[pair.target_view_id].source.sha256,images[pair.reference_view_id].source.sha256,
            "visible" if complete else "unknown","visible" if complete else "unknown",
            fingerprint({"context":context,"pair":pair.dependency_fingerprint}),
            _lineage(reference,target,views),len(samples)))
        if len(results) >= max_pairs:
            break
    return tuple(results)


def analyze_appearance(view_set, inputs, *, surface=None, view_settings=None, regions=(),
                       region_anchors=(), upstream_reports=(), policy=None,
                       vision_analyzer=None, cancel=None):
    """Inspect immutable source buffers without changing views, mesh or paint.

    A qualified host analyzer can supply optional identity evidence. The default
    requires identity and abstains when none is qualified. ``require_identity``
    may explicitly narrow acceptance to measured color; it never certifies it.
    """
    policy = policy or AppearancePolicy()
    started = time.monotonic()
    deadline = started+policy.max_seconds
    settings = {view.view_id:(view_settings or {}).get(view.view_id,AppearanceViewSettings()) for view in view_set.views}
    ids = set(settings)
    regions,region_anchors,upstream_reports = tuple(regions),tuple(region_anchors),tuple(upstream_reports)
    if set(inputs)-ids or set(view_settings or {})-ids:
        raise ValueError("Appearance inputs/settings must name this exact view revision.")
    if len(regions)+len(region_anchors) > policy.max_regions or len(upstream_reports)>20:
        raise ValueError("Appearance region/upstream bounds exceeded.")
    if any(r.view_id not in ids for r in regions) or any(a.region.view_id not in ids for a in region_anchors):
        raise ValueError("Appearance regions must name original views in this revision.")
    regions = tuple(dict.fromkeys((*regions,*(a.region for a in region_anchors))))
    if len({a.region for a in region_anchors}) != len(region_anchors):
        raise ValueError("A region can have only one declared surface anchor.")
    findings,pairs,view_results = [],[],[]
    completion,semantic = "complete",None
    sampler = None
    samples = 0
    source_hash = _source_hash()
    image_fingerprints,decoded = [],{}
    upstream_hashes = tuple(fingerprint(report.to_dict()) for report in upstream_reports)
    settings_hashes = tuple(sorted((key,value.dependency_fingerprint) for key,value in settings.items()))
    context = fingerprint({"view_set":view_set.dependency_dict(),"surface":surface.to_dict() if surface else None,
        "settings":settings_hashes,"regions":[r.to_dict() for r in regions],
        "region_anchors":[a.to_dict() for a in region_anchors],"policy":asdict(policy),
        "upstream":upstream_hashes,"source":source_hash})

    def emit(code,status,message,view_ids=(),*,region=None,measurements=(),required=True,artifact=None,key=""):
        token = fingerprint({"code":code,"views":view_ids,"region":region.to_dict() if region else None,"key":key})[:24]
        evidence = Evidence("e-"+token,"observation",message,tuple(view_ids),
            (region,) if region else (),tuple(measurements) or (Measurement("supported",int(status=="pass"),"count"),),artifact)
        findings.append(Finding("d4-"+token,code,"appearance","info" if status=="pass" else "warning",status,
            message,tuple(view_ids),(region,) if region else (),evidence=(evidence,),required=required,
            reason=message if status in ("unknown","not_applicable") else ""))

    # Upstream quality is composed as immutable evidence; semantics never votes
    # a failed geometry/export report away, even if all color samples match.
    upstream_ok = True
    for index,report in enumerate(upstream_reports):
        current = report.view_set.dependency_fingerprint == view_set.dependency_fingerprint
        status = report.verification_status.value if current else "unknown"
        upstream_ok &= status == "pass"
        emit("quality.upstream_status",status,"Upstream quality is preserved; stale revisions abstain.",
             artifact=ArtifactReference("upstream-"+str(index),upstream_hashes[index],"application/json"),key=str(index))

    try:
        check_budget(deadline,cancel)
        count = sum((r.width*r.height if type(r.width) is int and type(r.height) is int and r.width>0 and r.height>0 else policy.max_total_pixels+1)
                    for data in inputs.values() for r in (data.image,data.mask) if r is not None)
        observations = [v for v in view_set.views if v.role == "observation"]
        references = [v for v in view_set.views if v.role == "reference"]
        if len(view_set.views)>policy.max_views or len(observations)>policy.max_observations or len(references)>policy.max_references or count>policy.max_total_pixels:
            raise OverflowError("Appearance input/view pixel budget exceeded.")
        # D1 reproduces hashes, segmentation and camera evidence on the actual
        # input buffers. D4 does not reuse a merely declared successful report.
        preflight = analyze_preflight(view_set,inputs).report
        retained = [f for f in preflight.findings if f.category in ("input","camera")]
        findings.extend(replace(f,finding_id="d4-input-"+f.finding_id) for f in retained)
        invalid = {vid for f in retained if f.required and f.status != "pass" for vid in f.view_ids}
        valid = ids-invalid
        for key in sorted(valid):
            decoded[key] = inputs[key].image.decoded_sha256
            image_fingerprints.append((key,inputs[key].image.source_sha256,decoded[key]))
        context = fingerprint({"dependencies":context,"decoded":image_fingerprints})
        if surface is None:
            emit("appearance.surface","unknown","A declared normalized triangle surface is required for visibility-aware comparison.")
        elif surface.binding_sha256 is not None and surface.binding_sha256 != view_set.dependency_fingerprint:
            emit("appearance.surface","fail","The surface belongs to another view revision; correspondence was not attempted.")
        else:
            canonical = view_set.canonical_reference
            accepted = bool(canonical and canonical.validated and canonical.validation_evidence)
            refs = [r for r in references if r.view_id in valid and accepted and r.view_id in canonical.view_ids]
            obs = [v for v in observations if v.view_id in valid]
            allowed = {}
            for target in obs:
                allowed[target.view_id] = []
                for reference in refs:
                    lineage = _lineage(reference,target,view_set.views)
                    if lineage == "accepted":
                        allowed[target.view_id].append(reference)
                    else:
                        emit("appearance.canonical_reference","unknown","Reference ancestry is "+lineage+"; it cannot judge this target.",
                             (target.view_id,reference.view_id),key=lineage)
            if not refs or not obs or not any(allowed.values()):
                emit("appearance.canonical_reference","unknown","Independent accepted canonical views and calibrated observations are required.")
            sampler = SurfaceSampler(surface,deadline=deadline,cancel=cancel,max_work=policy.max_work,min_facing=policy.min_facing)
            masks = {key:mask_from_input(inputs[key],.1,.5) for key in valid}
            cache = {}
            for view in (*obs,*refs):
                opposite = allowed[view.view_id] if view.role == "observation" else [v for v in obs if view in allowed[v.view_id]]
                width,height = _grid(inputs[view.view_id],policy.sampling_size)
                # Bound both geometric grids and every emitted pair raster;
                # adding references must not multiply output allocations for free.
                cost = width*height*(1+len(opposite))
                if samples+cost > policy.max_samples:
                    raise OverflowError("Appearance sample budget exceeded.")
                samples += cost
                mapping = sampler.map_views(view,opposite,width=width,height=height)
                current_pairs = []
                for other in opposite:
                    check_budget(deadline,cancel)
                    target,reference = (view,other) if view.role == "observation" else (other,view)
                    pair = compare_pair(mapping,target_id=target.view_id,reference_id=reference.view_id,
                        inputs=inputs,settings=settings,subject_masks=masks,policy=policy,deadline=deadline,cancel=cancel,color_cache=cache)
                    current_pairs.append(pair)
                    pairs.append(pair)
                conflicts = canonical_conflicts(mapping,current_pairs,policy.color_tolerance) if view.role == "observation" else ()
                if conflicts:
                    emit("appearance.canonical_reference","unknown","Accepted canonical colors conflict at the same visible surface points.",conflicts,key=view.view_id)
                result = aggregate_view(mapping,current_pairs,data=inputs[view.view_id],role=view.role.value,
                    settings=settings[view.view_id],requested_regions=regions,region_anchors=region_anchors,
                    policy=policy,deadline=deadline,cancel=cancel)
                if conflicts or not upstream_ok:
                    result = replace(result,regions=tuple(replace(r,color_status="unknown",
                        reason="Canonical disagreement or upstream uncertainty prevents reliable appearance attribution.") for r in result.regions))
                view_results.append(result)
            # Any canonical disagreement suppresses attribution throughout the
            # group, including reverse maps evaluated before/after this one.
            if any(f.code == "appearance.canonical_reference" and "conflict" in f.message for f in findings):
                view_results = [replace(v,regions=tuple(replace(r,color_status="unknown",
                    reason="Conflicting accepted references prevent color attribution.") for r in v.regions)) for v in view_results]
            seen = {triangle for view in view_results for triangle in view.visible_triangles}
            emit("appearance.surface_coverage","unknown","Observed triangle hits are lower-bound evidence; unsampled surface area and hidden sides are not certified.",
                measurements=(Measurement("triangles_with_visible_hits",len(seen),"count"),Measurement("total_triangles",len(surface.triangles),"count")),required=False)
        check_budget(deadline,cancel)
        images = _snapshots(view_set,inputs,settings,valid,decoded,deadline,cancel)
        request = SemanticRequest(view_set,context,_semantic_pairs(pairs,view_set.views,images,context,128),images)
        semantic = analyze_semantics(request,analyzer=vision_analyzer,
            timeout_seconds=max(.001,min(120.,deadline-time.monotonic())),cancel=cancel)
        findings.extend(semantic.findings)
        if semantic.state == "cancelled":
            completion = "cancelled"
        elif semantic.state == "timed_out":
            completion = "partial"
        check_budget(deadline,cancel)
    except InterruptedError:
        completion = "cancelled"
        emit("appearance.compute_budget","unknown","Appearance analysis was cancelled; partial evidence is retained.")
    except (TimeoutError,OverflowError) as exc:
        completion = "partial"
        emit("appearance.compute_budget","unknown",str(exc))

    for view in view_results:
        for region in view.regions:
            measurements = tuple(Measurement(name,value,"sample") for name,value in (
                ("expected",region.expected_samples),("visible",region.visible_samples),
                ("comparable",region.comparable_samples),("changed",region.changed_samples)))
            emit("appearance.coverage",region.coverage_status,
                "Coverage of the declared original-image region; hidden or unanchored support remains unresolved.",
                (view.view_id,),region=region.region,measurements=measurements)
            emit("appearance.color_consistency",region.color_status,region.reason,(view.view_id,),region=region.region,measurements=measurements)
    for code in ("appearance.coverage","appearance.color_consistency"):
        if not any(f.code==code for f in findings):
            emit(code,"unknown","No supported visible calibrated region could be compared.")
    for pair in pairs:
        emit("appearance.lighting_variation","unknown" if not settings[pair.target_view_id].calibrated or not settings[pair.reference_view_id].calibrated else "pass",
            "Photometry is producer-declared evidence; fitted gain is diagnostic only and never establishes calibration.",
            (pair.target_view_id,pair.reference_view_id),key=pair.pair_id,required=False)
        if pair.fitted_neutral_gain is not None:
            emit("appearance.lighting_transform","unknown","A neutral gain fit may explain a residual but cannot prove a lighting cause.",
                (pair.target_view_id,pair.reference_view_id),key=pair.pair_id,required=False,
                measurements=(Measurement("fitted_gain",pair.fitted_neutral_gain,"ratio"),)+(
                    (Measurement("fitted_residual",pair.fitted_residual,"linear-channel-distance"),)
                    if pair.fitted_residual is not None else ()))
    identity = "unknown"
    if semantic is not None and semantic.qualification_evidence is not None and "identity" in semantic.qualification_kinds and semantic.state == "complete" and upstream_ok:
        claims = [claim for claim in semantic.claims if claim.kind=="identity"]
        if claims and all(c.status in ("pass","fail") for c in claims):
            identity = "fail" if any(c.status=="fail" for c in claims) else "pass"
    emit("appearance.identity_assessment",identity,
        "Identity requires visible evidence and host-declared model qualification; adapter mocks and unavailable analyzers cannot certify it.",
        required=policy.require_identity,artifact=semantic.qualification_evidence if semantic else None)
    engines = {ENGINE.engine_id:ENGINE}
    if semantic is not None:
        for engine in semantic.engines:
            if engine.engine_id in engines and engines[engine.engine_id] != engine:
                raise ValueError("Semantic engine version conflicts with the appearance engine.")
            engines[engine.engine_id] = engine
    assumptions = (
        "Declared normalized mesh, camera and photometry evidence are producer assertions, not measured physical truth.",
        "Only sampled corresponding visible source pixels are compared; no mirroring or intentional-asymmetry penalty.",
        "Unseen surface area and unqualified identity remain unknown; confidence is not a probability.",
        "appearance-context:"+context,
        "appearance-source:"+source_hash,
    )
    if semantic is not None:
        assumptions += ("semantic-dependency:"+semantic.dependency_fingerprint,)
    report = DiagnosticReport("appearance-"+context[:24],view_set,tuple(engines.values()),policy.contract(),
        DiagnosticResolution(policy.sampling_size,policy.sampling_size),tuple(findings),assumptions,completion)
    provenance = AppearanceProvenance(source_hash,context,surface.sha256 if surface else None,
        tuple(image_fingerprints),upstream_hashes,settings_hashes,samples,
        min(sampler.work_units,policy.max_work) if sampler else 0,policy.max_samples,policy.max_work,
        time.monotonic()-started,policy.max_seconds)
    return AppearanceResult(report,surface,tuple(view_results),tuple(pairs),semantic,upstream_reports,provenance)
