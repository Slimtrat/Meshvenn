"""The installable Sketch package contains no reconstruction-engine payload."""
import importlib.util
from pathlib import Path
import tempfile
import tomllib
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('build_sketch',ROOT/'scripts/build_meshvenn_sketch.py')
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackageTests(unittest.TestCase):
    def test_reproducible_self_contained_zip_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as folder:
            first=builder.build(Path(folder)/'first.zip')
            second=builder.build(Path(folder)/'second.zip')
            self.assertEqual(first.read_bytes(),second.read_bytes())
            before=first.read_bytes()
            with self.assertRaises(FileExistsError):builder.build(first)
            self.assertEqual(first.read_bytes(),before)
            with zipfile.ZipFile(first) as archive:
                names=set(archive.namelist())
                self.assertTrue({'__init__.py','blender_manifest.toml','README.md','LICENSE'}<=names)
                self.assertTrue(all('/' not in name for name in names))
                self.assertEqual({n for n in names if n.endswith('.py')},
                                 {p.name for p in builder.SOURCE.glob('*.py')})
                manifest=tomllib.loads(archive.read('blender_manifest.toml').decode())
                self.assertEqual(manifest['id'],'meshvenn_sketch')
                self.assertLessEqual(len(manifest['tagline']),64)
                self.assertTrue(all(len(v)<=64 for v in manifest['permissions'].values()))


if __name__=='__main__':unittest.main()
