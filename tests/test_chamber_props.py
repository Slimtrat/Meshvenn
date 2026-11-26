"""Delivery regression gates for the rigid Stytch fixtures, no Blender required."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from chamber_props.validate import verify, glb
from build_stytch_chamber_pack import build

PACK=ROOT/'example/v2/props/StytchChamberV1'


class ChamberDeliveryTests(unittest.TestCase):
    def copy(self,folder):
        return Path(shutil.copytree(PACK,Path(folder)/'pack'))

    def test_two_rigid_embedded_pbr_props(self):
        doc=verify(PACK)
        self.assertEqual([a['triangles'] for a in doc['assets']],[2988,3224])
        self.assertEqual(doc['coordinates'],dict(up='+Y',front='+Z',units='metres'))
        for asset in doc['assets']:
            data=glb(PACK/asset['file'])
            self.assertNotIn('skins',data)
            self.assertEqual(len(data['meshes']),2)
            self.assertEqual(len(data['images']),3)

    def test_complete_portable_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            output=build(PACK,Path(folder)/'delivery.zip')
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                archive.extractall(Path(folder)/'unpacked')
                self.assertIn('scripts/chamber_props/godot_smoke.gd',archive.namelist())
                self.assertIn('scripts/chamber_props/author.py',archive.namelist())
                self.assertIn('LICENSE',archive.namelist())
            verify(Path(folder)/'unpacked')
            with self.assertRaises(FileExistsError):build(PACK,output)

    def test_tampered_glb_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            pack=self.copy(folder)
            with (pack/'chamber-door-v1.glb').open('ab') as stream:stream.write(b'corrupt')
            with self.assertRaisesRegex(ValueError,'Fingerprint'):verify(pack)

    def test_missing_source_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            pack=self.copy(folder);(pack/'chamber-door-v1.blend').unlink()
            with self.assertRaises(FileNotFoundError):verify(pack)

    def test_stale_proof_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            pack=self.copy(folder);path=pack/'godot-validation.json'
            proof=json.loads(path.read_text());proof['assets'][0]['sha256']='0'*64
            path.write_text(json.dumps(proof))
            with self.assertRaisesRegex(ValueError,'Stale godot proof'):build(pack,Path(folder)/'bad.zip')

    def test_foreign_clip_refused_even_with_updated_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            pack=self.copy(folder);path=pack/'pack.json'
            manifest=json.loads(path.read_text());manifest['assets'][0]['animations']=['old_door_clip']
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'animation clips'):verify(pack)

    def test_texture_path_escape_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            pack=self.copy(folder);path=pack/'pack.json'
            manifest=json.loads(path.read_text());manifest['textures'][0]['file']='../outside.png'
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'escapes'):verify(pack)


if __name__=='__main__':unittest.main()
