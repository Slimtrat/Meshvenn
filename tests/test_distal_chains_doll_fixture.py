"""Immutable distal-chain delivery with strict authority and bounded pose evidence."""
import hashlib
import json
from pathlib import Path
import struct
import unittest

from core.modular_character import ModularCharacterSpec
from scripts.extract_stytch_pose_series import capture_profile
from scripts.workshop_doll_evidence import compare_limb_variant, compare_reference
from tests.test_authored_skin_doll_fixture import reader

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'example/v2/modular/StytchDollShoulderAligned'
FIXTURE = BASE.parent / 'StytchDollDistalChains'
BASE_SHA = '6654f85acb539e471ccc525f4ffc029409e96e98aeb524df1be95211e860d3f8'
GLB_SHA = '58bb85ca53f4bc437b7eb62777ea2d25aeb84aee7b46c4a53f837a507f89849b'
SOURCE_SHA = 'c02f6e29fc215366f891e75f4179e519aeaaa665f5b4feac6c7a41d8d237ae33'
GENERATOR_SHA = 'a990a163a7845c03a8d3c99f5aa70b5e866527f4'


def read(path):
    return json.loads(path.read_text('utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DistalChainsDollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest,cls.quality=read(FIXTURE/'manifest.json'),read(FIXTURE/'pose-quality.json')
        cls.old,cls.old_binary=reader.read_glb(BASE/'character.glb')
        cls.new,cls.new_binary=reader.read_glb(FIXTURE/'character.glb')
        cls.positions=read(FIXTURE/'edited-source-positions.json')

    def test_distinct_pinned_delivery_and_edit_mask_provenance(self):
        self.assertEqual(digest(BASE/'character.glb'),BASE_SHA)
        self.assertEqual(digest(BASE/'source.blend'),'7d424323bfb70d7cd5abdd36af034ea30f30c210989f35677ef7b4049c71adbd')
        self.assertEqual(digest(FIXTURE/'character.glb'),GLB_SHA)
        self.assertEqual(digest(FIXTURE/'source.blend'),SOURCE_SHA)
        self.assertEqual(self.manifest['sha256'],GLB_SHA)
        self.assertEqual(self.manifest['editable_source_sha256'],SOURCE_SHA)
        self.assertEqual(self.quality['source_sha'],GENERATOR_SHA)
        self.assertEqual(self.manifest['pose_quality_report_sha256'],digest(FIXTURE/'pose-quality.json'))
        for document in (self.manifest,self.quality):
            self.assertEqual(document['edited_source_positions_sha256'],digest(FIXTURE/'edited-source-positions.json'))
        for name,key in (('authoring.json','authoring_sha256'),('partition-authoring.json','partition_authoring_sha256')):
            self.assertEqual((FIXTURE/name).read_bytes(),(BASE/name).read_bytes())
            self.assertEqual(digest(FIXTURE/name),self.manifest[key])
        for path in FIXTURE.glob('*.json'):
            self.assertNotIn(b'\r',path.read_bytes())
        self.assertEqual((FIXTURE/'reference.glb').read_bytes(),(BASE/'reference.glb').read_bytes())

    def test_contract_surface_binds_atlas_and_undeclared_weights_are_preserved(self):
        proof=compare_limb_variant(self.old,self.old_binary,self.new,self.new_binary,reader.read_accessor,self.positions)
        self.assertEqual(proof,self.manifest['reference_fidelity'])
        self.assertTrue(proof['weights_outside_declared_positions_exact'])
        self.assertTrue(proof['native_inverse_binds_exact'])
        self.assertTrue(proof['surface_uv_material_atlas_preserved'])
        self.assertEqual(proof['declared_edited_position_count'],597)
        spec=self.new['asset']['extras']['meshvenn_modular_character']['spec']
        self.assertEqual(spec,self.old['asset']['extras']['meshvenn_modular_character']['spec'])
        parsed=ModularCharacterSpec.from_dict(spec)
        self.assertEqual((len(parsed.regions),len(parsed.sockets)),(5,8))
        self.assertEqual(len(self.new['skins'][0]['joints']),18)
        self.assertFalse(self.new.get('animations'))
        self.assertTrue(self.manifest['roundtrip']['passed'])
        self.assertEqual(self.manifest['roundtrip']['raw_normal_tolerance'],2e-6)
        with self.assertRaisesRegex(ValueError,'skin influences|source weights'):
            compare_reference(self.old,self.old_binary,self.new,self.new_binary,reader.read_accessor)

    def test_separate_edit_proof_rejects_undeclared_rows_atlas_and_binds(self):
        def check(binary,positions):
            compare_limb_variant(self.old,self.old_binary,self.new,binary,reader.read_accessor,positions)
        with self.assertRaisesRegex(ValueError,'outside the declared'):
            check(self.new_binary,self.positions[:1])
        with self.assertRaisesRegex(ValueError,'finite'):
            check(self.new_binary,[(float('nan'),0,0)])
        changed=bytearray(self.new_binary)
        view=self.new['bufferViews'][self.new['images'][0]['bufferView']]
        changed[view.get('byteOffset',0)]^=1
        with self.assertRaisesRegex(ValueError,'atlas'): check(bytes(changed),self.positions)
        changed=bytearray(self.new_binary)
        accessor=self.new['accessors'][self.new['skins'][0]['inverseBindMatrices']]
        view=self.new['bufferViews'][accessor['bufferView']]
        offset=view.get('byteOffset',0)+accessor.get('byteOffset',0)+48
        struct.pack_into('<f',changed,offset,struct.unpack_from('<f',changed,offset)[0]+1)
        with self.assertRaisesRegex(ValueError,'inverse binds'): check(bytes(changed),self.positions)

    def test_distal_root_rotations_eliminate_rigid_chain_drift(self):
        before,after=self.quality['root_rigid_baseline'],self.quality['root_rigid_candidate']
        self.assertEqual(len(before),8)
        self.assertEqual(len(after),8)
        for old,new in zip(before,after):
            self.assertEqual((old['role'],old['angle_degrees']),(new['role'],new['angle_degrees']))
            self.assertEqual(old['vertex_count'],new['vertex_count'])
            self.assertGreater(new['vertex_count'],0)
            self.assertLess(new['max_rigid_residual_in_heights'],2e-6)
            if old['max_rigid_residual_in_heights']>1e-4:
                self.assertLessEqual(new['max_rigid_residual_in_heights'],.01*old['max_rigid_residual_in_heights'])
        edit=self.manifest['limb_chain_refinement']
        self.assertEqual(edit['algorithm'],'authored-distal-native-chains-v1')
        self.assertEqual(edit['changed_vertex_count'],597)
        self.assertTrue(edit['native_rest_joints_unchanged'])
        self.assertTrue(edit['body_interfaces_and_chain_only_rows_exact'])

    def test_thirty_two_isolated_controls_bound_real_tradeoffs(self):
        before,after=self.quality['isolated_baseline'],self.quality['isolated_candidate']
        self.assertEqual(len(before),32)
        self.assertEqual(len(after),32)
        for old,new in zip(before,after):
            self.assertEqual(old['id'],new['id'])
            self.assertEqual(old['edges']['edge_count'],new['edges']['edge_count'])
            for metric in ('p95_abs_log_length_ratio','max_abs_log_length_ratio'):
                self.assertLessEqual(new['edges'][metric],1.01*old['edges'][metric]+1e-4)
            self.assertLessEqual(new['edges']['collapsed_fraction'],old['edges']['collapsed_fraction']+1e-10)

    def test_nineteen_captured_matrix_replays_preserve_transport_and_protected_vertices(self):
        profile=capture_profile('shoulder-aligned')
        index=read(profile['dataset']/'index.json')
        expected={c['id']:c for c in index['cases']}
        self.assertEqual(self.quality['pose_set_sha256'],profile['index_sha256'])
        self.assertEqual(self.quality['consumer_pose_revision'],profile['revision'])
        self.assertEqual(self.quality['captured_asset_sha256'],BASE_SHA)
        self.assertEqual(self.quality['candidate_sha256'],GLB_SHA)
        self.assertEqual(self.quality['editable_source_sha256'],SOURCE_SHA)
        self.assertEqual(self.quality['case_count'],19)
        self.assertEqual(len(self.quality['cases']),19)
        self.assertEqual({c['id'] for c in self.quality['cases']},set(expected))
        for case in self.quality['cases']:
            for key in ('probe_sha256','matrix_proof_sha256','hidden_regions'):
                self.assertEqual(case[key],expected[case['id']][key])
            for key in ('source_vs_decoded_max_error_m','decoded_vs_reimport_max_error_m','protected_vertices_pose_max_error_m'):
                self.assertLess(case[key],2e-5*1.82)
            self.assertLess(case['rest_world_matrix_max_error'],2e-6)
            self.assertLess(abs(case['candidate_torso_edges']['p95_abs_log_length_ratio']-case['baseline_torso_edges']['p95_abs_log_length_ratio']),1e-4)
            self.assertEqual(len(case['candidate_visible_joint_edges']),6)
            for name,current in case['candidate_owned_joint_edges'].items():
                role=('left-' if name.endswith('.L') else 'right-')+('arm' if name.startswith('forearm') else 'leg')
                self.assertNotIn(role,case['hidden_regions'])
                old=case['baseline_owned_joint_edges'][name]
                self.assertEqual(current['edge_count'],old['edge_count'])
                self.assertLessEqual(current['max_abs_log_length_ratio'],1.01*old['max_abs_log_length_ratio']+1e-4)
                self.assertLessEqual(current['collapsed_fraction'],old['collapsed_fraction']+1e-10)
            for side,current in case['candidate_visible_hip_edges'].items():
                old=case['baseline_visible_hip_edges'][side]
                self.assertLessEqual(current['max_abs_log_length_ratio'],old['max_abs_log_length_ratio']+1e-4)
                self.assertLessEqual(current['collapsed_fraction'],old['collapsed_fraction']+1e-10)

    def test_own_comparison_images_and_acceptance_limits_remain_explicit(self):
        self.assertEqual(len(self.quality['images']),16)
        for name,sha in self.quality['images'].items():
            self.assertEqual(Path(name).name,name)
            self.assertEqual(digest(FIXTURE/'poses'/name),sha)
        self.assertFalse(self.quality['consumer_capture_targets_candidate'])
        self.assertFalse(self.quality['visual_qualification'])
        self.assertFalse(self.quality['consumer_acceptance'])
        self.assertTrue(self.quality['native_rests_and_captured_matrices_unchanged'])
        self.assertIn('NOT replayed',self.manifest['consumer_acceptance'])
        self.assertIn('p95 remains diagnostic',self.quality['isolated_gate'])
        self.assertTrue(self.manifest['remaining_limits'])


if __name__=='__main__': unittest.main()
