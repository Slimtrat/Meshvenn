"""The real visual comparison must work on CPU without Workbench/EGL."""
import os
import json
from pathlib import Path
import tempfile
import unittest

from scripts.character_quality.render import render_comparison
from scripts.diagnostic_qualification.integrity import sha256_file, verify_file

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/diagnostics/provider-v1/original-reference.glb"


class HeadlessCharacterRenderTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("MESHVENN_TEST_BLENDER"), "Blender rendering not configured")
    def test_real_cpu_render_records_backend_and_exact_geometry_for_both_modes(self):
        digest = sha256_file(SOURCE)
        assets = [{"asset_id": name, "role": role, "label": name,
                   "glb_path": str(SOURCE), "glb_sha256": digest}
                  for name, role in (("source", "source"), ("result", "candidate"))]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "review"
            result = render_comparison(assets, root, blender_executable=Path(os.environ["MESHVENN_TEST_BLENDER"]),
                                       angles=(45,), size=128, timeout_seconds=120)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["render_backend"]["engine"], "CYCLES")
            self.assertEqual(result["render_backend"]["device"], "CPU")
            self.assertFalse(result["render_backend"]["denoising"])
            meshes = [json.loads((root / a["mesh"]["path"]).read_text()) for a in result["assets"]]
            def surface(mesh):
                return sorted(tuple(sorted(tuple(mesh["vertices"][i]) for i in triangle)) for triangle in mesh["triangles"])
            # Imported object names/ordering can differ; world-space triangles cannot.
            self.assertEqual(surface(meshes[0]), surface(meshes[1]))
            for asset in result["assets"]:
                self.assertEqual(asset["reload"]["source_glb_sha256"], digest)
                self.assertEqual(len(asset["frames"]), 6)
                self.assertEqual({f["mode"] for f in asset["frames"]}, {"flat", "material"})
                for frame in asset["frames"]:
                    self.assertEqual(verify_file(root, frame)["status"], "pass")
                    self.assertGreater(frame["bytes"], 1000)


if __name__ == "__main__":
    unittest.main()
