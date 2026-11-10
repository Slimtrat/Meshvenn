"""Frozen source-edge measurements on exact captured poses; not acceptance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.author_stytch_doll import digest,module,source_snapshot
from scripts.extract_stytch_pose_series import CAPTURE_PROFILES
from scripts.glb_v2_pose_metrics import joint_edge_summary
from scripts.glb_v2_pose_support import evaluated_positions
from scripts.native_pose_replay import apply_probe
from scripts.report_stytch_pose_coverage import load_capture_cases

JOINTS=tuple(f'{stem}.{side}' for stem in ('forearm','thigh','shin') for side in ('L','R'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=CAPTURE_PROFILES,default='distal-chains')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-sha',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    output=args.output.resolve()
    if output.exists():raise ValueError('Choose a fresh report; existing evidence stays immutable.')
    profile,index,prepared=load_capture_cases(args.profile)
    fixture=profile['fixture'];manifest=json.loads((fixture/'manifest.json').read_text('utf-8'))
    if digest(fixture/'character.glb')!=profile['asset_sha256'] or digest(fixture/'source.blend')!=manifest['editable_source_sha256']:
        raise ValueError('Source or selected GLB fingerprint changed.')
    bpy.ops.wm.open_mainfile(filepath=str(fixture/'source.blend'),use_scripts=False)
    mesh,rig=bpy.data.objects['MeshvennScan'],bpy.data.objects['MeshvennCanonicalRig']
    before=source_snapshot(mesh,rig)
    original_pose=rig.data.pose_position
    bases={bone.name:bone.matrix_basis.copy() for bone in rig.pose.bones}
    try:
        for bone in rig.pose.bones:bone.matrix_basis.identity()
        rig.data.pose_position='POSE';bpy.context.view_layer.update()
        rest=evaluated_positions(mesh)
        height=max(p[2] for p in rest)-min(p[2] for p in rest)
        mesh.data.calc_loop_triangles()
        triangles=[tuple(t.vertices) for t in mesh.data.loop_triangles]
        spec=module('implementations.glb_export.face_authoring')._read(fixture/'authoring.json')
        roles={r.id:r.role for r in spec.regions}
        face_roles=[roles[r] for r in spec.ownership[mesh.name]]
        tri_roles=[face_roles[t.polygon_index] for t in mesh.data.loop_triangles]
        centres={name:tuple(rig.matrix_world @ rig.data.bones[name].head_local) for name in JOINTS}
        owner={name:('left-' if name.endswith('.L') else 'right-')+('arm' if name.startswith('forearm') else 'leg') for name in JOINTS}
        cases=[]
        for case,_,probe in prepared:
            error=apply_probe(rig,probe)
            posed=evaluated_positions(mesh)
            full={name:joint_edge_summary(rest,posed,triangles,centres[name],height,touching=True) for name in JOINTS}
            present={}
            for name in JOINTS:
                if owner[name] in case['hidden_regions']:continue
                selected=[t for t,role in zip(triangles,tri_roles) if role in {'body-core',owner[name]}]
                present[name]=joint_edge_summary(rest,posed,selected,centres[name],height,touching=True)
            cases.append({'id':case['id'],'probe_sha256':case['probe_sha256'],
                'matrix_proof_sha256':case['matrix_proof_sha256'],'hidden_regions':case['hidden_regions'],
                'native_applied_delta_error':error,'full_joint_edges':full,'present_owned_joint_edges':present,
                **({'elbow_excitation':case['elbow_excitation']} if 'elbow_excitation' in case else {})})
        if source_snapshot(mesh,rig)!=before:raise ValueError('Measurement changed source authority.')
    finally:
        for bone in rig.pose.bones:bone.matrix_basis=bases[bone.name]
        rig.data.pose_position=original_pose;bpy.context.view_layer.update()
    if source_snapshot(mesh,rig)!=before:raise ValueError('Source authority did not restore exactly.')
    report={'schema_version':1,'source_sha':args.source_sha,'capture_profile':args.profile,
        'asset_sha256':profile['asset_sha256'],'editable_source_sha256':manifest['editable_source_sha256'],
        'source_authority_sha256':hashlib.sha256(json.dumps(before,sort_keys=True,allow_nan=False).encode()).hexdigest(),
        'consumer_revision':index['source_revision'],'dataset_sha256':profile['index_sha256'],
        'case_count':len(cases),'cases':cases,'source_authority_unchanged':True,'pose_state_restored':True,
        'native_rest_centres_m':centres,'joint_radius_in_heights':.12,
        'cohort_policy':'Frozen source-rest joint balls, either edge endpoint within 0.12 heights. Full mesh diagnostic is separate from body+owned-limb triangles, reported only when that limb is present. No hidden-joint quality credit.',
        'measurements_completed':True,'visual_qualification':False,'consumer_acceptance':False,
        'scope':'Source-only edge-length distortion on actual selected-asset matrices. This is not an anatomy, volume, self-intersection, contact or artistic certificate. Strict source/raw/reimport transport is separately reported by series replay.'}
    payload=json.dumps(report,indent=2,allow_nan=False)+'\n'
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8',newline='\n') as stream:stream.write(payload)
    print(f'Measured {len(cases)} actual source poses; source and pose state restored. Visual acceptance remains false.')


if __name__=='__main__':main()
