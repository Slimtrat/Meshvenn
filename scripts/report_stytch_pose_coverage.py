"""Report what the exact captured poses actually exercise, without Blender."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.modular_character.json_io import strict_json_loads
from core.native_pose_capture import REGIONS,validate_matrix_proof
from core.native_pose_probe import NativePoseProbe
from scripts.extract_stytch_pose_series import CAPTURE_PROFILES,capture_profile
from scripts.native_pose_coverage import summarize_joint_motion


def load_capture_cases(profile_name,dataset=None):
    """Complete preflight before reports, rendering or other output publication."""
    profile=capture_profile(profile_name)
    dataset=(dataset or profile['dataset']).resolve(strict=True)
    index_path=dataset/'index.json'
    if hashlib.sha256(index_path.read_bytes()).hexdigest()!=profile['index_sha256']:
        raise ValueError('Series index differs from the explicitly qualified capture revision.')
    index=strict_json_loads(index_path.read_text('utf-8'))
    if index['asset_sha256']!=profile['asset_sha256'] or index['source_revision']!=profile['revision']:
        raise ValueError('Series lineage differs from the selected immutable asset/profile.')
    cases=index['cases']
    count=profile['case_count']
    if index['case_count']!=count or len(cases)!=count or len({c['id'] for c in cases})!=count:
        raise ValueError(f'Series requires {count} unique captured poses from the pinned profile.')
    prepared=[]
    for case in cases:
        if not isinstance(case['id'],str) or re.fullmatch(r'[A-Za-z0-9_-]{1,80}',case['id']) is None:
            raise ValueError('Unsafe capture case identifier.')
        paths=[]
        for key in ('probe','matrix_proof'):
            path=(dataset/case[key]).resolve(strict=True)
            if path.parent!=dataset or hashlib.sha256(path.read_bytes()).hexdigest()!=case[key+'_sha256']:
                raise ValueError('Unsafe or mismatched captured matrix file.')
            paths.append(path)
        probe=NativePoseProbe.from_dict(strict_json_loads(paths[0].read_text('utf-8')))
        if probe.asset_sha256!=index['asset_sha256']:
            raise ValueError('Pose series targets a different native asset.')
        validate_matrix_proof(probe,strict_json_loads(paths[1].read_text('utf-8')))
        hidden=case['hidden_regions']
        if (not isinstance(hidden,list) or any(not isinstance(r,str) or r not in REGIONS-{'body-core'} for r in hidden)
                or hidden!=sorted(set(hidden))):
            raise ValueError('Duplicate or unsorted hidden region provenance.')
        if profile_name=='distal-chains':
            from scripts.distal_consumer_capture import validate_projected_excitation
            validate_projected_excitation(case,probe)
        prepared.append((case,paths[0],probe))
    return profile,index,prepared


def coverage_report(profile_name, *, dataset=None,source_sha='local-uncommitted'):
    profile,index,prepared=load_capture_cases(profile_name,dataset)
    coverage=summarize_joint_motion([{'id':case['id'],'probe':probe,'hidden_regions':case['hidden_regions']}
                                     for case,_,probe in prepared])
    report={'source_sha':source_sha,'capture_profile':profile_name,'consumer_revision':index['source_revision'],
            'dataset_sha256':profile['index_sha256'],'matrices_validated':True,
            'case_fingerprints':[{k:case[k] for k in ('id','probe_sha256','matrix_proof_sha256','hidden_regions')} for case,_,_ in prepared],
            'joint_motion_coverage':coverage}
    report.update(context_motion_coverage(profile_name,prepared))
    return report


def context_motion_coverage(profile_name,prepared):
    """Isolated tests and Hop must not disguise missing held/walk articulation."""
    if profile_name!='distal-chains':return {}
    groups={'production':lambda c:'elbow_excitation' not in c,
            'isolated-elbows':lambda c:'elbow_excitation' in c,
            'walk':lambda c:c['id'].startswith('Walk-'),
            'held':lambda c:c['id']=='factory-held',
            'hop':lambda c:c['id'].startswith('Hop-')}
    return {'motion_context_coverage':{
        name:summarize_joint_motion([{'id':c['id'],'probe':probe,'hidden_regions':c['hidden_regions']}
                                    for c,_,probe in prepared if include(c)])
        for name,include in groups.items()}}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=CAPTURE_PROFILES,default='shoulder-aligned')
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-sha',default='local-uncommitted')
    args=parser.parse_args(argv)
    output=args.output.resolve()
    if output.exists():raise ValueError('Choose a new coverage report; pinned evidence stays immutable.')
    report=coverage_report(args.profile,dataset=args.dataset,source_sha=args.source_sha)
    payload=json.dumps(report,indent=2,allow_nan=False)+'\n'
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(payload)
    missing=report['joint_motion_coverage']['missing_visible_rotation_excitation']
    print('Capture matrices validated. Missing visible local rotation excitation:',', '.join(missing) or 'none')
    print('Rotation excitation is not deformation or consumer acceptance.')


if __name__=='__main__':main()
