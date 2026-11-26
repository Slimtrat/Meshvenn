"""Frozen capture angles and SHA-bound evidence for the optional 18-view input."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

from scripts.character_quality.camera_profiles import (
    ADDITIONAL_CAMERAS, DENSE_CAMERAS, DENSE_PROFILE, LEGACY_CAMERAS,
)
from scripts.character_quality.fidelity import WITHHELD_CAMERA_ANGLES, _input_binding


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_png(value):
    """Distinct valid PNG bytes keep each minimal camera record independent."""
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+
            chunk(b'IDAT',zlib.compress(bytes((0,value,0,0,255))))+chunk(b'IEND',b''))


class DenseCameraProfileTests(unittest.TestCase):
    def test_capture_profile_preserves_the_original_ten_then_adds_real_intermediate_angles(self):
        expected_legacy = (
            ('az000',0,0.), ('az045',45,0.), ('az090',90,0.), ('az135',135,0.),
            ('az180',180,0.), ('az225',225,0.), ('az270',270,0.), ('az315',315,0.),
            ('top',0.,-90.), ('bottom',0.,90.),
        )
        expected_extra = (
            ('az022_5',22.5,0.), ('az067_5',67.5,0.), ('az112_5',112.5,0.), ('az157_5',157.5,0.),
            ('az202_5',202.5,0.), ('az247_5',247.5,0.), ('az292_5',292.5,0.), ('az337_5',337.5,0.),
        )
        self.assertEqual(LEGACY_CAMERAS, expected_legacy)
        self.assertEqual(ADDITIONAL_CAMERAS, expected_extra)
        self.assertEqual(DENSE_CAMERAS, expected_legacy+expected_extra)
        self.assertEqual(len({name for name,_,_ in DENSE_CAMERAS}), 18)
        self.assertEqual(DENSE_PROFILE, 'native-cube-18-input-v1')

    def test_withheld_evaluation_angles_are_never_reconstruction_inputs(self):
        self.assertEqual(WITHHELD_CAMERA_ANGLES, (30,120,210,300))
        input_azimuths = {az for _,az,elevation in DENSE_CAMERAS if elevation == 0}
        self.assertTrue(input_azimuths.isdisjoint(WITHHELD_CAMERA_ANGLES))
        self.assertFalse(any(name.startswith('withheld') for name,_,_ in DENSE_CAMERAS))


class DenseInputEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dense-view-binding-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # This guard verifies byte provenance only, not GLB parsing or rendering.
        self.source = self.write_artifact('source.glb',b'source artifact for binding test')
        candidate = self.write_artifact('candidate.glb',b'candidate artifact for binding test')
        self.case = {'id':'views18_organic','view_ids':[name for name,_,_ in DENSE_CAMERAS],
                     'input_camera_profile':DENSE_PROFILE,'glb':candidate}
        self.manifest = {'complete':True,'source':{'glb':self.source},'cases':[self.case],
                         'cameras':[{'id':name,'azimuth_degrees':az,'elevation_degrees':elevation,
                                     'flip_x':False,'png':self.write_artifact(name+'.png',pixel_png(i+1))}
                                    for i,(name,az,elevation) in enumerate(DENSE_CAMERAS)]}

    def write_artifact(self, name, data):
        path = self.root/name
        path.write_bytes(data)
        return {'path':name,'bytes':len(data),'sha256':digest(path)}

    def bind(self):
        case_path, manifest_path = self.root/'case.json', self.root/'manifest.json'
        case_path.write_text(json.dumps(self.case),encoding='utf-8')
        manifest_path.write_text(json.dumps(self.manifest),encoding='utf-8')
        return {'glb_sha256':self.case['glb']['sha256'],
                'input_evidence_path':str(case_path),'input_evidence_sha256':digest(case_path),
                'reconstruction_manifest_path':str(manifest_path),
                'reconstruction_manifest_sha256':digest(manifest_path)}

    def test_complete_dense_capture_is_accepted_with_all_original_byte_links(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(_input_binding(self.bind(),self.source['sha256']),self.case['view_ids'])
        self.assertEqual(len(self.case['view_ids']),18)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()
                                 if p.name not in ('case.json','manifest.json')})
        self.assertEqual(len({c['png']['sha256'] for c in self.manifest['cameras']}),18)

    def test_incomplete_dense_input_list_cannot_claim_the_complete_profile(self):
        self.case['view_ids'].pop()
        with self.assertRaises(ValueError):
            _input_binding(self.bind(),self.source['sha256'])

    def test_complete_dense_inputs_require_the_exact_versioned_profile(self):
        for profile in (None, 'native-cube-18-input-v2-unrecognized'):
            with self.subTest(profile=profile):
                if profile is None:
                    self.case.pop('input_camera_profile',None)
                else:
                    self.case['input_camera_profile'] = profile
                with self.assertRaises(ValueError):
                    _input_binding(self.bind(),self.source['sha256'])

    def test_dense_profile_claim_with_only_legacy_inputs_is_rejected(self):
        # Removing every extra view must not silently turn an 18-view claim
        # into accepted legacy evidence.
        self.case['view_ids'] = [name for name,_,_ in LEGACY_CAMERAS]
        with self.assertRaises(ValueError):
            _input_binding(self.bind(),self.source['sha256'])

    def test_missing_selected_camera_record_is_rejected(self):
        self.manifest['cameras'].pop()
        with self.assertRaises(ValueError):
            _input_binding(self.bind(),self.source['sha256'])

    def test_rehashed_opposite_forged_angle_or_flip_cannot_impersonate_a_new_capture(self):
        original = deepcopy(self.manifest['cameras'][-1])
        for changes in ({'azimuth_degrees':157.5}, {'azimuth_degrees':30.},
                        {'elevation_degrees':.1}, {'flip_x':True}):
            with self.subTest(changes=changes):
                self.manifest['cameras'][-1] = dict(original,**changes)
                # Rehashing outer JSON must not bypass fixed physical angles.
                with self.assertRaises(ValueError):
                    _input_binding(self.bind(),self.source['sha256'])

    def test_changed_png_bytes_are_rejected_even_when_outer_json_is_current(self):
        selected = self.manifest['cameras'][-1]['png']
        (self.root/selected['path']).write_bytes(pixel_png(250))
        with self.assertRaisesRegex(ValueError,'SHA256'):
            _input_binding(self.bind(),self.source['sha256'])

    def test_duplicate_input_ids_or_camera_records_are_rejected(self):
        ids = self.case['view_ids'][:]
        self.case['view_ids'][-1] = self.case['view_ids'][0]
        with self.assertRaises(ValueError):
            _input_binding(self.bind(),self.source['sha256'])
        self.case['view_ids'] = ids
        self.manifest['cameras'].append(deepcopy(self.manifest['cameras'][0]))
        with self.assertRaises(ValueError):
            _input_binding(self.bind(),self.source['sha256'])

    def test_changed_source_or_candidate_file_breaks_the_glb_binding(self):
        for record in (self.source,self.case['glb']):
            path = self.root/record['path']; original = path.read_bytes()
            path.write_bytes(original+b'changed')
            with self.subTest(path=path.name), self.assertRaisesRegex(ValueError,'SHA256'):
                _input_binding(self.bind(),self.source['sha256'])
            path.write_bytes(original)

    def test_legacy_camera_subset_remains_valid_without_a_dense_claim(self):
        self.case['view_ids'] = [name for name,_,_ in LEGACY_CAMERAS]
        self.case.pop('input_camera_profile')
        self.assertEqual(_input_binding(self.bind(),self.source['sha256']),self.case['view_ids'])


class RealDenseCaptureTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('MESHVENN_TEST_BLENDER') and os.environ.get('MESHVENN_TEST_NATIVE_LIBRARY'),
                         'Real Blender/native reconstruction not configured')
    def test_actual_eighteen_view_hull_extends_same_ten_inputs_and_reloads_glbs(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'dense'
            process = subprocess.run([os.environ['MESHVENN_TEST_BLENDER'], '--background', '--factory-startup',
                '--python-exit-code', '1', '--python', str(root/'scripts/character_quality/reconstruct.py'), '--',
                '--native-library', os.environ['MESHVENN_TEST_NATIVE_LIBRARY'], '--output', str(output),
                '--resolution', '32', '--mask-size', '64', '--hero-size', '64', '--view-counts', '10', '18'],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            manifest = json.loads((output/'manifest.json').read_text())
            self.assertTrue(manifest['complete'])
            self.assertEqual(len(manifest['cameras']), 18)
            self.assertEqual([c['id'] for c in manifest['cameras'][:10]], [n for n,_,_ in LEGACY_CAMERAS])
            cases = {c['id']:c for c in manifest['cases']}
            self.assertEqual(set(cases), {'views10_none','views10_organic','views18_none','views18_organic'})
            self.assertLessEqual(cases['views18_none']['native_volume']['occupied_voxels'],
                                 cases['views10_none']['native_volume']['occupied_voxels'])
            for case in cases.values():
                self.assertTrue(case['reload']['verified'])
                self.assertFalse(case['canonical_transform']['per_case_fit'])
                self.assertEqual(case['glb']['sha256'],digest(output/case['glb']['path']))
            self.assertEqual(cases['views18_organic']['input_camera_profile'], DENSE_PROFILE)
            self.assertEqual(len(cases['views18_organic']['view_ids']), 18)


if __name__ == '__main__':
    unittest.main()
