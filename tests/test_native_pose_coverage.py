"""Rotation excitation must not be mistaken for inherited motion or acceptance."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from core.native_pose_capture import multiply
from core.native_pose_probe import NativePoseProbe
from scripts.extract_stytch_pose_series import capture_profile
from scripts.native_pose_coverage import REQUIRED_JOINTS,joint_region,local_motion,summarize_joint_motion
from scripts.report_stytch_pose_coverage import coverage_report,load_capture_cases,main
from scripts.shoulder_pose_derivation import components
from tests.test_native_pose_probe import synthetic_probe

IDENTITY=((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.))


def rotation(angle):
    c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
    return ((1.,0.,0.,0.),(0.,c,-s,0.),(0.,s,c,0.),(0.,0.,0.,1.))


def case(identifier='pose',angles=None,hidden=None):
    value=synthetic_probe()
    for bone in value['Bones']:
        if bone['Name'] in (angles or {}):bone['Pose']=components(rotation(angles[bone['Name']]))
    return {'id':identifier,'probe':NativePoseProbe.from_dict(value),'hidden_regions':hidden or []}


class NativePoseCoverageTests(unittest.TestCase):
    def test_known_signed_rotations_cancel_nontrivial_rest_and_origin(self):
        rest=tuple((*row[:3],translation) for row,translation in zip(rotation(37),(2.,-4.,9.,1.)))
        for angle in (-180,-90,-45,0,45,90,180):
            measured=local_motion(rest,multiply(rest,rotation(angle)))
            self.assertTrue(measured['rigid_delta'])
            self.assertAlmostEqual(measured['rotation_degrees'],abs(angle),places=10)
            self.assertAlmostEqual(measured['translation_in_capture_units'],0,places=10)

    def test_float32_scale_roundoff_does_not_invent_trace_angle(self):
        perturbed=((.9999999,0.,0.,0.),(0.,.9999999,0.,0.),(0.,0.,.9999999,0.),(0.,0.,0.,1.))
        self.assertGreater(math.degrees(math.acos((3*.9999999-1)/2)),.03)
        self.assertEqual(local_motion(IDENTITY,perturbed)['rotation_degrees'],0)

    def test_parent_rotation_never_counts_as_child_articulation(self):
        report=summarize_joint_motion([case(angles={'upper_arm.L':90})])
        self.assertEqual(report['joints']['upper_arm.L']['visible_excited_cases'],['pose'])
        self.assertEqual(report['joints']['forearm.L']['max_local_rotation_degrees'],0)
        self.assertEqual(report['joints']['forearm.L']['visible_excited_cases'],[])
        self.assertFalse(report['visible_rotation_excitation_complete'])

    def test_hidden_joint_motion_cannot_earn_visible_rotation_credit(self):
        cases=[case('absent',{'shin.R':90},['right-leg']),case('present')]
        row=summarize_joint_motion(cases)['joints']['shin.R']
        self.assertEqual(row['max_local_rotation_degrees'],90)
        self.assertEqual(row['max_visible_local_rotation_degrees'],0)
        self.assertEqual(row['visible_case_count'],1)
        self.assertEqual(row['hidden_excited_cases'],['absent'])
        self.assertEqual(row['visible_excited_cases'],[])

    def test_nonrigid_scale_shear_and_translation_do_not_earn_rotation_credit(self):
        for transform in (((1.2,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.)),
                          ((1.,.1,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.))):
            document=synthetic_probe();document['Bones'][7]['Pose']=components(multiply(rotation(90),transform))
            report=summarize_joint_motion([{'id':'nonrigid','probe':NativePoseProbe.from_dict(document),'hidden_regions':[]}])
            row=report['joints']['forearm.L']
            self.assertIsNone(row['max_local_rotation_degrees'])
            self.assertEqual(row['nonrigid_cases'],['nonrigid'])
            self.assertEqual(row['visible_excited_cases'],[])
        translated=tuple((*r[:3],t) for r,t in zip(IDENTITY,(2.,3.,4.,1.)))
        measured=local_motion(IDENTITY,translated)
        self.assertEqual(measured['rotation_degrees'],0)
        self.assertAlmostEqual(measured['translation_in_capture_units'],math.sqrt(29))

    def test_excitation_completion_does_not_claim_range_quality_or_acceptance(self):
        report=summarize_joint_motion([case(angles={n:90 for n in REQUIRED_JOINTS})],threshold_degrees=90)
        self.assertTrue(report['visible_rotation_excitation_complete'])
        self.assertFalse(report['visual_qualification'] or report['consumer_acceptance'])
        self.assertIn('not a qualified articulation range',report['scope'])
        for name in REQUIRED_JOINTS:self.assertEqual(report['joints'][name]['visible_excited_cases'],['pose'])

    def test_mixed_fingerprints_or_changed_rests_are_refused(self):
        for changed in ('asset','rest'):
            value=synthetic_probe()
            if changed=='asset':value['AssetSha256']='b'*64
            else:value['Bones'][7]['Rest'][9]=.01
            other={'id':'changed','probe':NativePoseProbe.from_dict(value),'hidden_regions':[]}
            with self.assertRaisesRegex(ValueError,'different assets|changed native rests'):
                summarize_joint_motion([case(),other])

    def test_invalid_threshold_names_case_provenance_and_visibility_are_refused(self):
        for threshold in (0,-1,181,True,math.nan,math.inf):
            with self.assertRaises(ValueError):summarize_joint_motion([case()],threshold_degrees=threshold)
        for required in ((),('unknown',),('shin.L','shin.L')):
            with self.assertRaises(ValueError):summarize_joint_motion([case()],required_joints=required)
        for bad in (case('../unsafe'),case(hidden=['body-core']),case(hidden=['left-leg','left-leg']),{**case(),'private':'forbidden'}):
            with self.assertRaises(ValueError):summarize_joint_motion([bad])
        with self.assertRaises(ValueError):summarize_joint_motion([])
        with self.assertRaises(ValueError):summarize_joint_motion([case(),case()])
        self.assertEqual(joint_region('forearm.R'),'right-arm')
        self.assertEqual(joint_region('root'),'body-core')
        with self.assertRaises(ValueError):joint_region('unknown')

    def test_exact_fresh_profile_exposes_elbow_gap_and_hidden_right_leg_peak(self):
        report=coverage_report('shoulder-aligned')
        coverage=report['joint_motion_coverage'];joints=coverage['joints']
        self.assertTrue(report['matrices_validated'])
        self.assertEqual(coverage['case_count'],19)
        self.assertEqual(coverage['missing_visible_rotation_excitation'],['forearm.L','forearm.R'])
        for side in ('L','R'):
            self.assertLess(joints['forearm.'+side]['max_visible_local_rotation_degrees'],1e-4)
        self.assertEqual(joints['shin.R']['visible_case_count'],6)
        self.assertAlmostEqual(joints['shin.R']['max_visible_local_rotation_degrees'],12.3545858,places=5)
        self.assertAlmostEqual(joints['shin.R']['max_local_rotation_degrees'],45.2015262,places=4)
        self.assertEqual(joints['shin.R']['hidden_excited_cases'],['World-03-one-leg-hop'])
        self.assertEqual(report['dataset_sha256'],capture_profile('shoulder-aligned')['index_sha256'])

    def test_original_profile_keeps_its_own_immutable_lineage(self):
        profile,index,prepared=load_capture_cases('original')
        report=coverage_report('original')
        self.assertEqual(len(prepared),19)
        self.assertEqual(report['dataset_sha256'],profile['index_sha256'])
        self.assertEqual(index['asset_sha256'],report['joint_motion_coverage']['captured_asset_sha256'])
        self.assertNotEqual(report['dataset_sha256'],coverage_report('shoulder-aligned')['dataset_sha256'])

    def test_python_311_arithmetic_keeps_the_report_and_excitation_decisions(self):
        def legacy_sum(values):
            total=0
            for value in values:total+=value
            return total
        expected=coverage_report('shoulder-aligned')
        with patch('core.native_pose_capture.sum',legacy_sum,create=True), \
                patch('scripts.shoulder_pose_derivation.sum',legacy_sum,create=True), \
                patch('scripts.native_pose_coverage.sum',legacy_sum,create=True):
            self.assertEqual(coverage_report('shoulder-aligned'),expected)

    def test_corrupt_index_probe_and_matrix_proof_fail_before_output(self):
        profile=capture_profile('shoulder-aligned')
        for kind in ('index','probe','proof'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as folder:
                dataset=Path(folder)/'dataset';output=Path(folder)/'untouched'/'coverage.json'
                shutil.copytree(profile['dataset'],dataset)
                index=json.loads((dataset/'index.json').read_text('utf-8'))
                selected=index['cases'][0]
                if kind=='index':
                    with (dataset/'index.json').open('ab') as stream:stream.write(b'\n')
                    with self.assertRaises(ValueError):main(['--dataset',str(dataset),'--output',str(output)])
                elif kind=='probe':
                    with (dataset/selected['probe']).open('ab') as stream:stream.write(b'\n')
                    with self.assertRaises(ValueError):main(['--dataset',str(dataset),'--output',str(output)])
                else:
                    proof_path=dataset/selected['matrix_proof']
                    proof=json.loads(proof_path.read_text('utf-8'));proof['rest_relative']['forearm.L'][9]+=.1
                    proof_path.write_text(json.dumps(proof),'utf-8')
                    selected['matrix_proof_sha256']=hashlib.sha256(proof_path.read_bytes()).hexdigest()
                    (dataset/'index.json').write_text(json.dumps(index),'utf-8')
                    qualified={**profile,'index_sha256':hashlib.sha256((dataset/'index.json').read_bytes()).hexdigest()}
                    with patch('scripts.report_stytch_pose_coverage.capture_profile',return_value=qualified):
                        with self.assertRaisesRegex(ValueError,'recompose'):main(['--dataset',str(dataset),'--output',str(output)])
                self.assertFalse(output.parent.exists())

    def test_cli_does_not_overwrite_existing_user_or_evidence_file(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'evidence.json';output.write_bytes(b'USER EVIDENCE')
            with self.assertRaisesRegex(ValueError,'immutable'):main(['--output',str(output)])
            self.assertEqual(output.read_bytes(),b'USER EVIDENCE')


if __name__=='__main__':unittest.main()
