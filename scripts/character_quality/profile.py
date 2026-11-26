"""Reference-relative observations with independent preservation gates.

Defaults were frozen with analytic controls before candidate evaluation. They
describe a sensitivity profile, not a universal preference for rounded shapes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

from .metrics import ALGORITHM

REQUIRED_GATES = ('surface_fscore','source_iou','target_iou','important_parts','coverage')


@dataclass(frozen=True)
class ComparisonProfile:
    profile_id: str = 'reference-relative-analytic-controls-v1'
    largest_planar_patch_increase: float = .03
    normal_moment8_increase: float = .05
    section_turning_increase: float = .08
    minimum_signal_count: int = 2

    def __post_init__(self):
        if type(self.profile_id) is not str or not self.profile_id:raise ValueError('A named comparison basis is required.')
        for name in ('largest_planar_patch_increase','normal_moment8_increase','section_turning_increase'):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=1:raise ValueError('Invalid declared comparison tolerance.')
        if type(self.minimum_signal_count) is not int or not 1<=self.minimum_signal_count<=3:
            raise ValueError('Invalid minimum independent signal count.')


def _finite(value): return type(value) in (int,float) and math.isfinite(value)
def _ratio(candidate,reference):return candidate/reference if _finite(candidate) and _finite(reference) and reference>0 else None
def _sha(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)


def _shape(reference,candidate,profile):
    signals={}
    for name,limit in (('largest_planar_patch_fraction',profile.largest_planar_patch_increase),('normal_moment8',profile.normal_moment8_increase)):
        before,after=reference.get(name),candidate.get(name)
        delta=after-before if _finite(before) and _finite(after) else None
        signals[name]=dict(reference=before,candidate=after,increase=delta,tolerance=limit,
            status='unknown' if delta is None else 'fail' if delta>limit else 'pass')
    sections=[];before={s['section_id']:s for s in reference.get('sections',[])};after={s['section_id']:s for s in candidate.get('sections',[])}
    for name,first in sorted(before.items()):
        second=after.get(name,{})
        comparable=first.get('status')==second.get('status')=='measured' and all(first.get(key)==second.get(key) for key in ('normal','offset'))
        delta=second['turning_concentration']-first['turning_concentration'] if comparable else None
        sections.append(dict(section_id=name,reference=first.get('turning_concentration'),candidate=second.get('turning_concentration'),
            increase=delta,loop_count_reference=first.get('loop_count'),loop_count_candidate=second.get('loop_count'),
            status='unknown' if delta is None else 'fail' if delta>profile.section_turning_increase else 'pass'))
    measured=[s for s in sections if s['status']!='unknown']
    section_status='fail' if any(s['status']=='fail' for s in sections) else 'pass' if measured else 'unknown'
    signals['section_turning']=dict(status=section_status,tolerance=profile.section_turning_increase,sections=sections)
    failures=sum(s['status']=='fail' for s in signals.values());known=sum(s['status']!='unknown' for s in signals.values())
    status='fail' if failures>=profile.minimum_signal_count else 'unknown' if failures or known<profile.minimum_signal_count else 'pass'
    return dict(shape_status=status,signals=signals,independent_signals_exceeding_profile=failures,
        interpretation='Increased faceting relative to this reference and declared sensitivity.' if status=='fail' else
            'No supported increase beyond the declared reference-relative profile.' if status=='pass' else
            'Insufficient or single-signal evidence; no style acceptance is inferred.')


def compare_quality(reference, candidate, *, preservation_gates=None, profile=None):
    """Preserve per-region results and all existing gates; never average acceptance."""
    profile=profile or ComparisonProfile();record=asdict(profile)
    result=dict(schema_version=1,algorithm='character-reference-comparison-v1',profile=record,
        profile_sha256=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        reference_mesh_sha256=reference.get('mesh_sha256'),candidate_mesh_sha256=candidate.get('mesh_sha256'),
        reference_glb_sha256=reference.get('source_glb_sha256'),candidate_glb_sha256=candidate.get('source_glb_sha256'),
        verification_status='unknown',style_assessment='human_required',not_an_asset_certificate=True,
        component_count_reference=reference.get('component_count'),component_count_candidate=candidate.get('component_count'))
    compatible=(reference.get('algorithm')==candidate.get('algorithm')==ALGORITHM and reference.get('frame_id')==candidate.get('frame_id')
        and reference.get('units')==candidate.get('units') and all(reference.get('policy',{}).get(name)==candidate.get('policy',{}).get(name)
            for name in ('position_tolerance','normal_tolerance')))
    result.update(frame_id=reference.get('frame_id'),units=reference.get('units'),frame_consistency_status='pass' if compatible else 'unknown')
    if compatible and reference.get('status')==candidate.get('status')=='measured':result.update(_shape(reference,candidate,profile))
    else:result.update(shape_status='unknown',signals={},interpretation='Frames, measurement completion or numerical authorities are not comparable.')
    result['size_observations']=dict(surface_area_ratio=_ratio(candidate.get('surface_area'),reference.get('surface_area')),
        enclosed_volume_ratio=_ratio(candidate.get('enclosed_volume'),reference.get('enclosed_volume')),
        reference_enclosed_volume=reference.get('enclosed_volume'),candidate_enclosed_volume=candidate.get('enclosed_volume'),
        note='Absolute source-frame sizes are retained, not fitted away; these do not replace independent distance/part gates.')
    before={r['region_id']:r for r in reference.get('regions',[])};after={r['region_id']:r for r in candidate.get('regions',[])};regions=[]
    for name,first in sorted(before.items()):
        second=after.get(name,{})
        valid=compatible and first.get('authority_sha256') is not None and all(first.get(key)==second.get(key) for key in ('authority_sha256','bounds','origin','axes'))
        area_ref,area_candidate=first.get('surface_area'),second.get('surface_area')
        presence='unknown'
        if valid and _finite(area_ref) and area_ref>0 and _finite(area_candidate):presence='fail' if area_candidate==0 else 'pass'
        shaped=_shape(first,second,profile) if valid and first.get('status')==second.get('status')=='measured' else dict(shape_status='unknown',signals={})
        regions.append(dict(region_id=name,authority_status='pass' if valid else 'unknown',surface_presence_status=presence,
            surface_area_ratio=_ratio(area_candidate,area_ref),reference_surface_area=area_ref,candidate_surface_area=area_candidate,**shaped))
    result['regions']=regions
    result['global_shape_status']=result['shape_status']
    if any(r['shape_status']=='fail' for r in regions):result['shape_status']='fail'
    elif result['shape_status']=='pass' and any(r['shape_status']=='unknown' for r in regions):result['shape_status']='unknown'
    supplied=preservation_gates or {};gates={}
    if type(supplied) is not dict:raise ValueError('Preservation gates must be named independent evidence records.')
    for name in sorted(set(REQUIRED_GATES)|set(supplied)):
        value=supplied.get(name)
        valid=type(value) is dict and value.get('status') in ('pass','fail','unknown') and _sha(value.get('evidence_sha256'))
        gates[name]=dict(value) if valid else dict(status='unknown',reason='Independent gate/evidence not supplied or malformed.')
    statuses=[gate['status'] for gate in gates.values()]+[r['surface_presence_status'] for r in regions]
    if not compatible or reference.get('coverage_status')!='measured' or candidate.get('coverage_status')!='measured':statuses.append('unknown')
    result['preservation_gates']=gates
    result['preservation_status']='fail' if 'fail' in statuses else 'unknown' if 'unknown' in statuses else 'pass'
    result['overall_status']='fail' if result['shape_status']=='fail' or result['preservation_status']=='fail' else 'unknown'
    result['limitations']=['Material roughness and smooth vertex normals are not geometric evidence.',
        'A low faceting signal cannot authorize deletion, volume loss, shortened parts or missing coverage.',
        'Topology component mergers are reported but are not automatically called missing semantic parts.',
        'All declared triangles contribute, including internal/overlapping sheets; this is not a visibility-weighted surface certificate.',
        'Enclosed volume sums closed component volumes and is not the Boolean union volume of overlapping parts.',
        'Source/candidate hashes and common-frame authority must be bound by the caller to actual reloaded GLBs.',
        'This analytic sensitivity profile is not calibrated aesthetic probability or general character qualification.']
    json.dumps(result,allow_nan=False)
    return result
