"""Measure visible native-local rotation excitation, independently of fidelity."""
from __future__ import annotations

import math
import re

from core.native_pose_capture import REGIONS, multiply
from core.native_pose_probe import NativePoseProbe, PARENTS
from scripts.shoulder_pose_derivation import inverse

REQUIRED_JOINTS = tuple(f'{part}.{side}' for part in ('forearm','thigh','shin') for side in ('L','R'))
RIGID_TOLERANCE = 2e-5  # Measurement eligibility, never a transport/proof tolerance.


def joint_region(name):
    if name not in PARENTS:
        raise ValueError('Unknown native joint.')
    if '.' not in name:
        return 'body-core'
    stem,side=name.split('.')
    return ('left-' if side=='L' else 'right-')+('arm' if stem in {'upper_arm','forearm','hand'} else 'leg')


def local_motion(rest,pose):
    """Exclude parent/world motion and distinguish scale/shear from rotation.

    atan2 avoids acos(trace) inventing ~0.03 degree rotations from float32 rest
    roundoff. Nonrigid deltas remain explicit and cannot earn excitation credit.
    """
    delta=multiply(inverse(rest),pose)
    error=max(abs(sum(delta[k][i]*delta[k][j] for k in range(3))-(i==j))
              for i in range(3) for j in range(3))
    rigid=error<=RIGID_TOLERANCE
    skew=(delta[2][1]-delta[1][2],delta[0][2]-delta[2][0],delta[1][0]-delta[0][1])
    rotation=math.degrees(math.atan2(math.sqrt(sum(v*v for v in skew)),sum(delta[i][i] for i in range(3))-1)) if rigid else None
    return {'rotation_degrees':rotation,'rigid_delta':rigid,
            'basis_orthogonality_error':error,
            'translation_in_capture_units':math.sqrt(sum(delta[i][3]**2 for i in range(3)))}


def summarize_joint_motion(cases, *, threshold_degrees=5., required_joints=REQUIRED_JOINTS):
    """Amplitude evidence only: one excited pose is not an accepted pose range."""
    cases=tuple(cases);required_joints=tuple(required_joints)
    if (not cases or type(threshold_degrees) not in (int,float)
            or not math.isfinite(threshold_degrees) or not 0<threshold_degrees<=180
            or not required_joints or any(n not in PARENTS for n in required_joints)
            or len(set(required_joints))!=len(required_joints)):
        raise ValueError('Require cases, a finite excitation threshold and unique native joint names.')
    seen,asset,rests=set(),None,None
    joints={name:{'region':joint_region(name),'visible_case_count':0,
                  'max_local_rotation_degrees':None,'max_visible_local_rotation_degrees':None,
                  'visible_excited_cases':[],'hidden_excited_cases':[],'nonrigid_cases':[],
                  'max_basis_orthogonality_error':0.,'max_relative_translation_in_capture_units':0.}
            for name in PARENTS}
    for case in cases:
        if not isinstance(case,dict) or set(case)!={'id','probe','hidden_regions'}:
            raise ValueError('Coverage consumes only a case identifier, probe and explicit visibility.')
        identifier,probe,hidden=case['id'],case['probe'],case['hidden_regions']
        if (not isinstance(identifier,str) or re.fullmatch(r'[A-Za-z0-9_-]{1,80}',identifier) is None
                or identifier in seen or not isinstance(probe,NativePoseProbe)
                or not isinstance(hidden,list) or any(not isinstance(r,str) or r not in REGIONS-{'body-core'} for r in hidden)
                or hidden!=sorted(set(hidden))):
            raise ValueError('Require unique safe case names, validated probes and explicit sorted absent limbs.')
        seen.add(identifier)
        current={b.name:b.rest for b in probe.bones}
        if asset is None:asset,rests=probe.asset_sha256,current
        if probe.asset_sha256!=asset or current!=rests:
            raise ValueError('Cannot combine different assets or changed native rests in one coverage report.')
        for bone in probe.bones:
            measured=local_motion(bone.rest,bone.pose)
            row=joints[bone.name];visible=row['region'] not in hidden
            row['visible_case_count']+=visible
            row['max_basis_orthogonality_error']=max(row['max_basis_orthogonality_error'],measured['basis_orthogonality_error'])
            row['max_relative_translation_in_capture_units']=max(row['max_relative_translation_in_capture_units'],measured['translation_in_capture_units'])
            if not measured['rigid_delta']:
                row['nonrigid_cases'].append(identifier);continue
            angle=measured['rotation_degrees']
            row['max_local_rotation_degrees']=max(angle,row['max_local_rotation_degrees'] or 0)
            if visible:row['max_visible_local_rotation_degrees']=max(angle,row['max_visible_local_rotation_degrees'] or 0)
            if angle>=threshold_degrees:
                row['visible_excited_cases' if visible else 'hidden_excited_cases'].append(identifier)
    missing=[name for name in required_joints if not joints[name]['visible_excited_cases']]
    # Eligibility/excitation decisions above use raw values. Only diagnostic
    # output suppresses last-bit Python 3.11 versus 3.12+ summation differences.
    for row in joints.values():
        for key in ('max_local_rotation_degrees','max_visible_local_rotation_degrees'):
            if row[key] is not None:row[key]=round(row[key],9)
        for key in ('max_basis_orthogonality_error','max_relative_translation_in_capture_units'):
            row[key]=round(row[key],12)
    return {'schema_version':1,'captured_asset_sha256':asset,'case_count':len(cases),
            'excitation_threshold_degrees':threshold_degrees,'rigid_delta_eligibility_tolerance':RIGID_TOLERANCE,
            'required_joints':list(required_joints),'joints':joints,
            'missing_visible_rotation_excitation':missing,'visible_rotation_excitation_complete':not missing,
            'visual_qualification':False,'consumer_acceptance':False,
            'scope':'Rest-relative native-local rotation amplitude and recorded presence only. Parent/world motion and hidden limbs cannot earn visible joint credit. One excited pose is not a qualified articulation range, deformation quality, contact or consumer acceptance.'}
