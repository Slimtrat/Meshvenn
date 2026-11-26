"""Strict snapshots and genuine common-frame Blender/BVH regression cases."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.character_quality.fidelity import measure_fidelity, ALL_CAMERAS, WITHHELD_CAMERA_ANGLES, IOU_GATE_PROFILE


class FidelityContractTests(unittest.TestCase):
    def test_profile_angles_are_fixed_before_measurements(self):
        self.assertEqual(WITHHELD_CAMERA_ANGLES, (30, 120, 210, 300))
        self.assertEqual(len(ALL_CAMERAS), 14)
        self.assertEqual(IOU_GATE_PROFILE, "per-view-min-v1")

    def test_reject_invalid_budget_without_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "missing"
            for values in ({"samples": True}, {"raster_size": 1024}, {"timeout_seconds": float("nan")}):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    measure_fidelity([], output, "missing", **values)
                self.assertFalse(output.exists())

    @unittest.skipUnless(os.environ.get("MESHVENN_TEST_BLENDER"), "Blender regression not configured")
    def test_real_bvh_cannot_hide_shift_shrink_or_toon_shape_by_fitting(self):
        code = '''
import sys, math
sys.path.insert(0, ROOT)
from mathutils import Vector
from scripts.character_quality.fidelity import _shared_frame, _triangles, _surface
points=[Vector(p) for p in ((-1,-.7,-.8),(1,-.7,-.8),(1,.7,-.8),(-1,.7,-.8),(-1,-.7,.8),(1,-.7,.8),(1,.7,.8),(-1,.7,.8))]
faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
center,longest=_shared_frame(points)
reference=_triangles(points,faces,center,longest)
same=_surface(reference,reference,512)
assert same['legacy_coarse']['fscore']==1., same
for name, changed in [('shift',[p+Vector((.5,.2,.3)) for p in points]),('shrink',[p*.5 for p in points])]:
    score=_surface(reference,_triangles(changed,faces,center,longest),512)['legacy_coarse']['fscore']
    assert score<.60, (name,score)
# An ellipsoid is different geometry even when its extent matches the box.
ell=[]; triangles=[]
for y in range(21):
    theta=math.pi*y/20
    for x in range(40):
        phi=math.tau*x/40
        ell.append(Vector((math.sin(theta)*math.cos(phi),.7*math.sin(theta)*math.sin(phi),.8*math.cos(theta))))
for y in range(20):
    for x in range(40):
        a=y*40+x;b=y*40+(x+1)%40;c=(y+1)*40+x;d=(y+1)*40+(x+1)%40
        triangles.extend(((a,b,c),(b,d,c)))
score=_surface(reference,_triangles(ell,triangles,center,longest),512)['legacy_coarse']['fscore']
assert score<.60, score
assert 'SOURCE' in same['distance_units']
print('FIDELITY_NO_FIT_TESTS_PASSED')
'''.replace("ROOT", repr(str(ROOT)))
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "fidelity_regression.py"
            script.write_text(code, encoding="utf-8")
            process = subprocess.run([os.environ["MESHVENN_TEST_BLENDER"], "--background", "--factory-startup",
                "--python-exit-code", "1", "--python", str(script)], capture_output=True, text=True, timeout=60)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertIn("FIDELITY_NO_FIT_TESTS_PASSED", process.stdout)

    @unittest.skipUnless(os.environ.get("MESHVENN_CHARACTER_FIDELITY_OUTPUT"), "real fidelity output not configured")
    def test_real_receipt_keeps_important_parts_unknown_and_exact_snapshots(self):
        import hashlib
        output = Path(os.environ["MESHVENN_CHARACTER_FIDELITY_OUTPUT"])
        result = json.loads((output / "fidelity.json").read_text())
        request = json.loads((output / "fidelity-request.json").read_text())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["request_sha256"], hashlib.sha256((output / "fidelity-request.json").read_bytes()).hexdigest())
        self.assertFalse(result["shared_frame"]["candidate_fit"])
        self.assertEqual(result["verification_status"], "unknown")
        for asset in result["assets"]:
            record = next(a for a in request["assets"] if a["asset_id"] == asset["asset_id"])
            for kind in ("mesh", "glb"):
                self.assertEqual(hashlib.sha256(Path(record[kind + "_path"]).read_bytes()).hexdigest(), asset[kind + "_sha256"])
            self.assertEqual(asset["gates"]["important_parts"]["status"], "unknown")
            self.assertEqual(len(asset["per_view_iou"]), 22 if len(record.get("bound_input_view_ids") or ()) == 18 else 14)
            self.assertEqual(asset["verification_status"], "unknown")


if __name__ == "__main__":
    unittest.main()
