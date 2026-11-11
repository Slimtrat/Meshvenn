"""Opt-in real sdist -> wheel -> isolated install integration, without network.

Run with MESHVENN_TEST_ENGINE_PACKAGING=1 after installing setuptools and wheel.
Native replay additionally uses the trusted MESHVENN_TEST_NATIVE_LIBRARY path.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("MESHVENN_TEST_ENGINE_PACKAGING") == "1",
                     "Set MESHVENN_TEST_ENGINE_PACKAGING=1 for standalone distribution integration.")
class EngineDistributionTests(unittest.TestCase):
    def command(self, arguments, *, cwd):
        child = subprocess.run([sys.executable, *arguments], cwd=cwd, capture_output=True, text=True, timeout=120)
        self.assertEqual(child.returncode, 0, child.stdout[-12000:] + child.stderr[-12000:])
        return child.stdout

    def test_sdist_builds_a_pure_wheel_and_runs_native_actions_outside_checkout(self):
        # No build dependency imports occur during normal unittest discovery.
        self.command(["-c", "import setuptools,wheel"], cwd=ROOT)
        with tempfile.TemporaryDirectory(prefix="meshvenn-standalone-") as temporary:
            folder = Path(temporary)
            self.assertFalse(folder.resolve().is_relative_to(ROOT.resolve()))
            distributions = folder / "dist"
            distributions.mkdir()
            self.command(["-c", "from setuptools.build_meta import build_sdist;import sys;build_sdist(sys.argv[1])",
                          str(distributions)], cwd=ROOT)
            source_archive, = distributions.glob("*.tar.gz")
            with tarfile.open(source_archive) as archive:
                for member in archive.getmembers():
                    destination = (folder / "unpacked" / member.name).resolve()
                    self.assertTrue(destination.is_relative_to((folder / "unpacked").resolve()))
                    self.assertFalse(member.issym() or member.islnk())
                    if member.isfile():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(archive.extractfile(member).read())
            extracted, = (folder / "unpacked").iterdir()
            self.assertFalse((extracted / "tests").exists())
            self.assertFalse((extracted / "native").exists())
            self.command(["-c", "from setuptools.build_meta import build_wheel;import sys;build_wheel(sys.argv[1])",
                          str(distributions)], cwd=extracted)
            wheel, = distributions.glob("*.whl")
            with ZipFile(wheel) as archive:
                names = archive.namelist()
                self.assertIn("meshvenn_engine/core/geometry_diagnostics/worker.py", names)
                self.assertNotIn("meshvenn_engine/core/material_inputs.py", names)
                self.assertFalse(any("projected_material/" in name or "native_mesh_builder.py" in name for name in names))
                for name in names:
                    if not name.endswith(".py"):
                        continue
                    tree = ast.parse(archive.read(name), filename=name)
                    for node in ast.walk(tree):
                        imported = ([part.name for part in node.names] if isinstance(node, ast.Import)
                                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                        self.assertFalse(any(item.split(".")[0] in {"bpy", "mathutils", "openai", "anthropic", "mcp"} for item in imported), name)
                    if name.startswith("meshvenn_engine/core/"):
                        source = ROOT / name.removeprefix("meshvenn_engine/")
                        self.assertEqual(archive.read(name), source.read_bytes(), name)
            site = folder / "site"
            self.command(["-m", "pip", "install", "--no-index", "--no-deps", "--target", str(site), str(wheel)], cwd=folder)
            from tests.test_engine_library import cube_arguments
            arguments = cube_arguments()
            arguments["policy"] = {"resolution": 16, "reprojection_size": 64, "max_seconds": 15}
            request = folder / "arguments.json"
            request.write_text(json.dumps(arguments), encoding="utf-8")
            native = os.environ.get("MESHVENN_TEST_NATIVE_LIBRARY") or os.environ.get("MESHVENN_TEST_NATIVE_DLL", "")
            script = r'''
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from meshvenn_engine import MeshvennEngine
from meshvenn_engine.core.geometry_diagnostics import GeometryResult
engine=MeshvennEngine(native_library=sys.argv[3] or None,python_executable=sys.executable)
assert set(engine.capabilities()['actions'])=={'engine.capabilities','views.preflight','geometry.diagnose','geometry.mesh'}
arguments=json.loads(Path(sys.argv[2]).read_text())
preflight=dict(arguments,policy={'required_cameras':[]})
assert engine.execute('views.preflight',preflight)['report']['completion']=='complete'
if sys.argv[3]:
    result=engine.execute('geometry.diagnose',arguments)
    assert result['verification_status']=='pass', result['report']
    quality=result.pop('verification_status')
    assert GeometryResult.from_dict(result).report.verification_status==quality
    assert result['volume']['occupied_count']>0
    mesh=engine.execute('geometry.mesh',{'volume':result['volume']})
    assert mesh['mesh']['vertex_count']>0
    assert mesh['verification_status']=='unknown'
    assert mesh['provenance']['isolation']=='subprocess'
assert 'bpy' not in sys.modules
checkout=Path(sys.argv[4]).resolve()
for name,module in tuple(sys.modules.items()):
    if not (name=='meshvenn_engine' or name.startswith('meshvenn_engine.') or name=='core' or name.startswith('core.')):
        continue
    filename=getattr(module,'__file__',None)
    assert not filename or not Path(filename).resolve().is_relative_to(checkout), filename
print('STANDALONE_ENGINE_PASS')
'''
            output = self.command(["-I", "-c", script, str(site), str(request), native, str(ROOT)], cwd=folder)
            self.assertIn("STANDALONE_ENGINE_PASS", output)


if __name__ == "__main__":
    unittest.main()
