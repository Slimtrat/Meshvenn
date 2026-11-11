"""Exercise the new pure APIs from the real extension copy list, outside checkout."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from tests.test_extension_packaging import core_package_sources


ROOT = Path(__file__).resolve().parents[1]


class DiagnosticPackagingTests(unittest.TestCase):
    def test_shipped_diagnostics_import_without_blender_or_checkout(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        sources = core_package_sources(workflow)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / 'extension-core.zip'
            with ZipFile(archive_path, 'w') as archive:
                for source in sorted(sources):
                    archive.write(source, 'blender_projection_tool/' + source.relative_to(ROOT).as_posix())
            script = '''
import importlib
import sys
sys.path.insert(0, sys.argv[1] + '/blender_projection_tool')
for name in ('core.diagnostic_contracts', 'core.diagnostics_preflight', 'core.geometry_diagnostics'):
    module = importlib.import_module(name)
    if 'extension-core.zip' not in module.__file__:
        raise RuntimeError('Imported checkout instead of the shipped ZIP: ' + module.__file__)
if 'bpy' in sys.modules:
    raise RuntimeError('Headless diagnostics imported Blender')
print('PACKAGED DIAGNOSTICS PASS')
'''
            result = subprocess.run(
                [sys.executable, '-I', '-c', script, str(archive_path)],
                cwd=directory, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PACKAGED DIAGNOSTICS PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
