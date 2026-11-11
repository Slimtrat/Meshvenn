"""Pinned public module assets, complete handoff and ownership semantics."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[3]
PACK=ROOT/'example/v2/modules/StytchWorkshopV1'
DOC=json.loads((PACK/'pack.json').read_text())


def document(path):
    raw=path.read_bytes()
    assert struct.unpack_from('<4sII',raw)==(b'glTF',2,len(raw))
    length,kind=struct.unpack_from('<II',raw,12);assert kind==0x4E4F534A
    return json.loads(raw[20:20+length])


class WorkshopPackTests(unittest.TestCase):
    def test_three_complete_families_and_explicit_ownership(self):
        self.assertEqual(Counter(m['category'] for m in DOC['modules']),{'equipment':3,'replacement':4,'accessory':3})
        self.assertEqual(len({m['id'] for m in DOC['modules']}),10)
        replacements=[m for m in DOC['modules'] if m['category']=='replacement']
        self.assertEqual({m['replaces_region'] for m in replacements},{'left-arm','right-arm','left-leg','right-leg'})
        self.assertTrue(all(m['replaces_region']==m['owner_region'] for m in replacements))
        self.assertFalse(any(m['replaces_region']=='body-core' for m in DOC['modules']))

    def test_all_sixteen_files_are_pinned_isolated_and_clip_free(self):
        counts=Counter()
        for module in DOC['modules']:
            for kind in ('skinned','attachment'):
                if kind not in module:continue
                record=module[kind];path=(PACK/record['file']).resolve()
                self.assertTrue(path.is_relative_to(PACK.resolve()))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),record['sha256'])
                data=document(path);self.assertEqual(len(data['meshes']),1);self.assertFalse(data.get('animations'))
                self.assertEqual(data['asset']['extras']['meshvenn_module_asset']['id'],module['id'])
                if kind=='skinned':
                    self.assertEqual(len(data['skins']),1);self.assertEqual(len(data['skins'][0]['joints']),18)
                    self.assertEqual({data['nodes'][n]['name'] for n in data['skins'][0]['joints']},set(DOC['target']['joint_profile']))
                else:
                    self.assertFalse(data.get('skins'));self.assertEqual(len(data['nodes']),1)
                    self.assertEqual(record['binding']['local_transform'],'identity')
                    self.assertTrue(record['binding']['inherits_native_normalization'])
                counts[kind]+=1
        self.assertEqual(counts,{'skinned':10,'attachment':6})

    def test_original_reference_is_unchanged_and_reports_are_complete(self):
        reference=ROOT/'example/v2/modular/StytchDollDistalChains'
        for field,name in (('character_sha256','character.glb'),('source_sha256','source.blend')):
            self.assertEqual(hashlib.sha256((reference/name).read_bytes()).hexdigest(),DOC['target'][field])
        report=json.loads((PACK/'validation.json').read_text());self.assertEqual(len(report['modules']),10)
        self.assertEqual(sum(m['pose_probes'] for m in report['modules']),72)
        self.assertTrue(report['source_preserved'])
        self.assertTrue(all(m['max_source_raw_error_m']<1e-5 and m['reimport_error_m']<1e-5 for m in report['modules']))
        self.assertLess(report['total_triangles'],25000)
        native=json.loads((PACK/'godot-validation.json').read_text())
        self.assertEqual((native['skinned_modules'],native['static_attachments'],native['native_skeletons'],native['owner_presence_checks']),(10,6,1,160))
        self.assertTrue(native['native_rests_preserved'])
        self.assertTrue(native['source_free_pck']);self.assertFalse(native['source_glbs_available'])
        self.assertEqual(native['runtime_modules'],10)
        self.assertEqual(native['runtime_owner_presence_checks'],160)
        self.assertTrue(native['runtime_native_rests_preserved'])
        self.assertEqual(native['runtime_cache_rejections'],9)
        self.assertTrue(native['stale_import_rejected']);self.assertTrue(native['runtime_failure_exit_verified'])
        self.assertTrue(native['tampered_import_rejected'])
        for module in DOC['modules']:
            scene=module['runtime_scene']
            self.assertEqual(scene['source_sha256'],module['skinned']['sha256'])
            self.assertEqual(hashlib.sha256((PACK/scene['file']).read_bytes()).hexdigest(),scene['sha256'])

    def test_delivery_zip_is_complete_reproducible_and_never_overwrites(self):
        spec=importlib.util.spec_from_file_location('build_workshop',ROOT/'scripts/build_stytch_workshop_pack.py')
        builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as folder:
            a=builder.build(Path(folder)/'a.zip');b=builder.build(Path(folder)/'b.zip')
            self.assertEqual(a.read_bytes(),b.read_bytes())
            with self.assertRaises(FileExistsError):builder.build(a)
            with zipfile.ZipFile(a) as archive:
                names=set(archive.namelist())
                self.assertTrue({'README.md','LICENSE','source.blend','pack.json','validation.json','godot-validation.json','godot_module_adapter.gd','Source/author.py','Source/glb.py'}<=names)
                self.assertEqual(len([p for p in names if p.endswith('.glb')]),16)
                self.assertEqual(len([p for p in names if p.startswith('runtime/') and p.endswith('.scn')]),10)
                self.assertEqual(len([p for p in names if p.startswith('previews/')]),6)
                self.assertFalse(any('core/' in p or p.endswith(('.dll','.pyd')) for p in names))


if __name__=='__main__':unittest.main()
