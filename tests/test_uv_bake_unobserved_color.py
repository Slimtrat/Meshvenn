import os
from pathlib import Path
import subprocess
import unittest


class UVBakeUnobservedColorTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('MESHVENN_TEST_BLENDER'),'Blender not configured')
    def test_actual_sampler_and_bake_keep_inferred_pixels_in_fallback_counts(self):
        script=Path(__file__).with_name('blender_uv_bake_unobserved_smoke.py')
        result=subprocess.run([os.environ['MESHVENN_TEST_BLENDER'],'--background','--factory-startup',
            '--python-exit-code','1','--python',str(script)],capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,(result.stdout+result.stderr)[-5000:])
        self.assertIn('UV_UNOBSERVED_COLOR:',result.stdout)
