"""Selected distal-skin captures: provenance, actual elbow excitation and privacy."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.native_pose_capture import CONVENTION,LAYOUT,multiply,project_capture,validate_matrix_proof
from core.native_pose_probe import NativePoseProbe,matrix_rows
from scripts import distal_consumer_capture as selected
from scripts import extract_stytch_pose_series as extractor
from scripts.native_pose_coverage import local_motion
from scripts.report_stytch_pose_coverage import coverage_report,load_capture_cases
from scripts.shoulder_pose_derivation import components

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'example/v2/poses/StytchDollDistalChains/complete'


def read(path):return json.loads(path.read_text('utf-8'))
def sha(data):return hashlib.sha256(data).hexdigest()
def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def raw_capture(case):
    doc,proof=read(FIXTURE/case['probe']),read(FIXTURE/case['matrix_proof'])
    context={**case['context'],'PRIVATE':'NEVER PUBLISH'}
    if 'elbow_excitation' in case:
        elbow=case['elbow_excitation']
        context.update(Left=elbow['joint'].endswith('.L'),RequestedDegrees=elbow['requested_degrees'],
                       MeasuredRestRelativeDegrees=elbow['measured_degrees'],Visible=True)
    return {**doc,'SchemaVersion':1,'MatrixLayout':LAYOUT,'PoseConvention':CONVENTION,
        'CaptureFile':case['capture_filename'],'CaptureSha256':case['capture_sha256'],'Context':context,
        'Regions':[{'Id':r,'Visible':r not in case['hidden_regions']} for r in ('body-core','left-arm','right-arm','left-leg','right-leg')],
        'Ancestors':[{**a,'Name':'PRIVATE'} for a in proof['ancestors']],
        'Mounts':['PRIVATE'],'Controls':['PRIVATE'],
        'Bones':[{**b,'RestRelative':proof['rest_relative'][b['Name']],
                  'SkeletonSpace':proof['skeleton_space'][b['Name']]} for b in doc['Bones']]}


def synthetic_private(folder):
    blobs={}
    for case in read(FIXTURE/'index.json')['cases']:
        name=case['source_path'].removeprefix(selected.SOURCE_BASE)
        path=folder/name;path.parent.mkdir(parents=True,exist_ok=True)
        raw=raw_capture(case);png=b'PRIVATE IMAGE BYTES'
        raw['CaptureSha256']=sha(png)
        data=extractor.encoded(raw);path.write_bytes(data)
        path.with_name(raw['CaptureFile']).write_bytes(png)
        blobs[name]=blob(data)
    return {**extractor.capture_profile('distal-chains'),'source_blobs':blobs,'index_sha256':'not-qualified'}


class DistalConsumerCapturesTests(unittest.TestCase):
    def test_twenty_three_pinned_pairs_target_the_delivered_distal_skin(self):
        profile,index,prepared=load_capture_cases('distal-chains')
        self.assertEqual(sha((FIXTURE/'index.json').read_bytes()),selected.INDEX_SHA256)
        self.assertEqual(index['source_revision'],selected.REVISION)
        self.assertEqual(index['asset_sha256'],selected.ASSET_SHA)
        self.assertEqual(len(prepared),23)
        self.assertEqual(profile['case_count'],23)
        self.assertEqual(len(list(FIXTURE.glob('*.json'))),47)
        self.assertEqual(list(FIXTURE.rglob('*.png')),[])
        for case,_,probe in prepared:
            name=case['source_path'].removeprefix(selected.SOURCE_BASE)
            self.assertEqual(case['source_git_blob'],selected.SOURCE_BLOBS[name])
            self.assertEqual(probe.asset_sha256,selected.ASSET_SHA)
            for key in ('probe','matrix_proof'):
                data=(FIXTURE/case[key]).read_bytes()
                self.assertEqual(sha(data),case[key+'_sha256'])
                self.assertNotIn(b'\r',data)
            validate_matrix_proof(probe,read(FIXTURE/case['matrix_proof']))
        fixture=profile['fixture']
        self.assertEqual(sha((fixture/'character.glb').read_bytes()),selected.ASSET_SHA)
        self.assertEqual(sha((fixture/'source.blend').read_bytes()),'c02f6e29fc215366f891e75f4179e519aeaaa665f5b4feac6c7a41d8d237ae33')

    def test_four_elbows_have_correct_angles_opposite_rest_and_visible_arms(self):
        cases=[c for c in read(FIXTURE/'index.json')['cases'] if 'elbow_excitation' in c]
        self.assertEqual(len(cases),4)
        self.assertEqual({(c['elbow_excitation']['joint'],c['elbow_excitation']['requested_degrees']) for c in cases},
                         {(f'forearm.{side}',angle) for side in ('L','R') for angle in (45,90)})
        for case in cases:
            raw=raw_capture(case);doc,_,meta=project_capture(raw)
            name=case['source_path'].removeprefix(selected.SOURCE_BASE)
            self.assertEqual(selected.elbow_excitation(name,raw,doc,meta),case['elbow_excitation'])
            self.assertTrue(case['elbow_excitation']['both_arms_visible'])
            self.assertLess(case['elbow_excitation']['opposite_degrees'],.05)
            self.assertNotIn('left-arm',case['hidden_regions']);self.assertNotIn('right-arm',case['hidden_regions'])

    def test_contradictory_elbow_annotations_and_presence_are_refused(self):
        case=next(c for c in read(FIXTURE/'index.json')['cases'] if 'elbow_excitation' in c)
        name=case['source_path'].removeprefix(selected.SOURCE_BASE)
        for key,value in (('Left',False),('RequestedDegrees',90),('RequestedDegrees',True),
                          ('Visible',False),('MeasuredRestRelativeDegrees',99),('MeasuredRestRelativeDegrees',float('nan'))):
            raw=raw_capture(case);raw['Context'][key]=value
            doc,_,meta=project_capture(raw)
            with self.assertRaises(ValueError):selected.elbow_excitation(name,raw,doc,meta)
        raw=raw_capture(case)
        next(r for r in raw['Regions'] if r['Id']=='right-arm')['Visible']=False
        doc,_,meta=project_capture(raw)
        with self.assertRaises(ValueError):selected.elbow_excitation(name,raw,doc,meta)

    def test_actual_delta_overrides_claimed_target_and_opposite_arm_annotation(self):
        case=next(c for c in read(FIXTURE/'index.json')['cases'] if 'elbow_excitation' in c)
        raw=raw_capture(case);doc,_,meta=project_capture(raw)
        name=case['source_path'].removeprefix(selected.SOURCE_BASE)
        inactive=copy.deepcopy(doc)
        b=next(b for b in inactive['Bones'] if b['Name']=='forearm.L');b['Pose']=list(b['Rest'])
        with self.assertRaises(ValueError):selected.elbow_excitation(name,raw,inactive,meta)
        opposite=copy.deepcopy(doc)
        b=next(b for b in opposite['Bones'] if b['Name']=='forearm.R')
        rotation=((1,0,0,0),(0,0,-1,0),(0,1,0,0),(0,0,0,1))
        b['Pose']=components(multiply(matrix_rows(b['Rest']),rotation))
        with self.assertRaises(ValueError):selected.elbow_excitation(name,raw,opposite,meta)

    def test_contexts_do_not_let_isolated_elbows_or_hop_qualify_walk_and_held(self):
        report=coverage_report('distal-chains');groups=report['motion_context_coverage']
        self.assertTrue(report['joint_motion_coverage']['visible_rotation_excitation_complete'])
        self.assertEqual({k:v['case_count'] for k,v in groups.items()},
                         {'production':19,'isolated-elbows':4,'walk':3,'held':1,'hop':12})
        for name in ('walk','held'):
            for side in ('L','R'):
                row=groups[name]['joints']['forearm.'+side]
                self.assertLess(row['max_visible_local_rotation_degrees'],1e-4)
                self.assertEqual(row['visible_excited_cases'],[])
        for side in ('L','R'):
            row=groups['hop']['joints']['forearm.'+side]
            self.assertGreater(row['max_visible_local_rotation_degrees'],75)
            self.assertEqual(len(row['visible_excited_cases']),12)
        self.assertFalse(report['joint_motion_coverage']['visual_qualification'])
        self.assertFalse(report['joint_motion_coverage']['consumer_acceptance'])

    def test_public_elbow_annotations_are_recomputed_without_private_inputs(self):
        _,_,prepared=load_capture_cases('distal-chains')
        case,_,probe=next(item for item in prepared if 'elbow_excitation' in item[0])
        changed=copy.deepcopy(case);changed['elbow_excitation']['measured_degrees']+=1
        with self.assertRaises(ValueError):selected.validate_projected_excitation(changed,probe)
        changed=copy.deepcopy(case);changed['elbow_excitation']['opposite_joint']='forearm.L'
        with self.assertRaises(ValueError):selected.validate_projected_excitation(changed,probe)
        changed=copy.deepcopy(case);changed['source_git_blob']='0'*40
        with self.assertRaises(ValueError):selected.validate_projected_excitation(changed,probe)

    def test_selected_profile_has_stable_python_311_diagnostic_arithmetic(self):
        def legacy_sum(values):
            total=0
            for value in values:total+=value
            return total
        expected=coverage_report('distal-chains')
        with patch('core.native_pose_capture.sum',legacy_sum,create=True), \
                patch('scripts.shoulder_pose_derivation.sum',legacy_sum,create=True), \
                patch('scripts.native_pose_coverage.sum',legacy_sum,create=True):
            self.assertEqual(coverage_report('distal-chains'),expected)

    def test_projection_preflights_all_inputs_then_publishes_only_whitelisted_data(self):
        with tempfile.TemporaryDirectory() as folder:
            source,output=Path(folder)/'private',Path(folder)/'public'
            profile=synthetic_private(source);captured={};encode=extractor.encoded
            def capture(value):
                data=encode(value)
                if isinstance(value,dict) and 'cases' in value:captured['index']=data
                return data
            with patch('scripts.extract_stytch_pose_series.capture_profile',return_value=profile), \
                    patch('scripts.extract_stytch_pose_series.encoded',side_effect=capture):
                with self.assertRaisesRegex(ValueError,'qualification pin'):extractor.main(['--profile','distal-chains','--input',str(source),'--output',str(output)])
            self.assertFalse(output.exists())
            profile['index_sha256']=sha(captured['index'])
            with patch('scripts.extract_stytch_pose_series.capture_profile',return_value=profile):
                extractor.main(['--profile','distal-chains','--input',str(source),'--output',str(output)])
            self.assertEqual(len(list(output.glob('*.json'))),47)
            for path in output.iterdir():
                self.assertEqual(path.suffix,'.json')
                text=path.read_text('utf-8')
                self.assertNotIn('PRIVATE',text)
                self.assertNotIn('RequestedDegrees',text)
                self.assertNotIn('Controls',text)

    def test_bad_png_proof_elbow_claim_and_index_fail_before_publication(self):
        for kind in ('png','proof','elbow','index'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as folder:
                source,output=Path(folder)/'private',Path(folder)/'public'
                profile=synthetic_private(source)
                name='Elbows/meshvenn-elbow-left-45.pose.json';path=source/name;raw=read(path)
                if kind=='png':path.with_name(raw['CaptureFile']).write_bytes(b'WRONG IMAGE')
                elif kind in ('proof','elbow'):
                    if kind=='proof':raw['Bones'][0]['RestRelative'][9]+=.1
                    else:raw['Context']['RequestedDegrees']=90
                    data=extractor.encoded(raw);path.write_bytes(data);profile['source_blobs'][name]=blob(data)
                with patch('scripts.extract_stytch_pose_series.capture_profile',return_value=profile):
                    with self.assertRaises(ValueError):extractor.main(['--profile','distal-chains','--input',str(source),'--output',str(output)])
                self.assertFalse(output.exists())

    def test_old_profiles_remain_nineteen_and_are_not_relabelled(self):
        for name in ('original','shoulder-aligned'):
            profile,index,prepared=load_capture_cases(name)
            self.assertEqual(profile['case_count'],19)
            self.assertEqual(len(prepared),19)
            self.assertNotEqual(index['asset_sha256'],selected.ASSET_SHA)
            self.assertNotIn('motion_context_coverage',coverage_report(name))


if __name__=='__main__':unittest.main()
