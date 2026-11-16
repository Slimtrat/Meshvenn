"""Frozen original 3D provenance; no generative provider is called or qualified."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from core.diagnostics_preflight import RasterInput
from core.projection_math import compile_projection
from core.projection_math.projection import projection_aligned_axes
from scripts.diagnostic_qualification.reference import FROZEN_MANIFEST_SHA256,verify_fixture

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/"tests/fixtures/diagnostics/provider-v1"


def pixels(name):
    raster=RasterInput.from_png_bytes((FIXTURE/name).read_bytes())
    if raster.error:raise AssertionError(raster.error)
    return raster.width,raster.height,bytes(round(c*255) for c in raster.rgba)


class ProviderReferenceTests(unittest.TestCase):
    def test_pinned_archive_does_not_claim_a_fresh_reload_or_human_qualification(self):
        result=verify_fixture(FIXTURE)
        self.assertEqual(result["manifest_sha256"],FROZEN_MANIFEST_SHA256)
        self.assertTrue(result["archived_reload_verified"])
        self.assertFalse(result["fresh_reload_performed"])
        manifest=result["manifest"]
        self.assertTrue(manifest["frozen_before_provider"])
        self.assertEqual(manifest["provider_calls"],0)
        self.assertFalse(manifest["human_reviewed"])
        self.assertFalse(manifest["provider_fidelity_qualified"])
        self.assertFalse(manifest["corrected_3d_claim"])
        self.assertEqual(manifest["license"],"GPL-3.0-or-later")

    def test_exact_glb_resources_and_original_component_inventory(self):
        result=verify_fixture(FIXTURE)
        self.assertEqual(result["resources"]["external_resources"],0)
        self.assertEqual(result["resources"]["embedded_buffers"],1)
        self.assertLess((FIXTURE/"original-reference.glb").stat().st_size,2*1024*1024)
        source=json.loads((FIXTURE/"original-source.json").read_bytes())
        proof=json.loads((FIXTURE/"glb-reload-proof.json").read_bytes())
        self.assertEqual(result["resources"]["meshes"],source["mesh_objects"])
        self.assertEqual(result["resources"]["triangles"],source["triangles"])
        self.assertIn("right_flag_only",source["expected_parts"])
        self.assertNotIn("left_flag_only",source["expected_parts"])
        self.assertTrue({"body","head","left_hand","right_hand","left_boot","right_boot","badge_color"}<=set(source["expected_parts"]))
        self.assertTrue(proof["reloaded_in_empty_scene"])
        self.assertLessEqual(proof["maximum_world_position_error"],proof["tolerance"])
        for name,before in proof["before"].items():
            after=proof["after"][name]
            self.assertEqual(before["triangles"],after["triangles"])
            self.assertEqual(before["geometric_components"],after["geometric_components"])
            self.assertTrue(all(-1<=a<=b<=1 for a,b in zip(before["minimum"],before["maximum"])))

    def test_cardinal_camera_declarations_match_the_native_projector_frame(self):
        cameras=verify_fixture(FIXTURE)["manifest"]["cameras"]
        for name,angle in (("front",0),("right",90),("back",180),("left",270)):
            camera=cameras[name]
            self.assertEqual(camera["azimuth_degrees"],angle)
            self.assertEqual(camera["elevation_degrees"],0)
            self.assertEqual(camera["ortho_scale"],2)
            self.assertFalse(camera["flip_x"])
            self.assertEqual(camera["alignment"],dict(offset_u=0.,offset_v=0.,scale=1.))
            direction=projection_aligned_axes(compile_projection(azimuth_degrees=angle,elevation_degrees=0))[2]
            length=math.hypot(*camera["location"])
            for actual,expected in zip(camera["location"],direction):
                self.assertAlmostEqual(actual/length,expected,places=6)
            self.assertLess(camera["maximum_native_uv_error"],2e-6)
            self.assertEqual((camera["width"],camera["height"]),(1024,1024) if name=="front" else (512,512))

    def test_frozen_provider_pair_changes_only_visible_badge_support(self):
        manifest=verify_fixture(FIXTURE)["manifest"]
        pair=manifest["provider_inputs"]
        self.assertTrue(pair["selection_frozen_before_provider"])
        self.assertTrue(pair["transparent_background"])
        width,height,before=pixels(pair["healthy"])
        w,h,after=pixels(pair["target"])
        self.assertEqual((width,height,w,h),(1024,1024,1024,1024))
        _,_,visible=pixels(pair["visible_mask"])
        _,_,editable=pixels(pair["edit_mask"])
        changed=visible_count=edit_count=changed_outside_centre=0
        for offset in range(0,len(before),4):
            v,e=visible[offset],editable[offset]
            self.assertIn(v,(0,255));self.assertIn(e,(0,255))
            self.assertEqual(visible[offset:offset+4],bytes((v,v,v,255)))
            self.assertEqual(editable[offset:offset+4],bytes((e,e,e,255)))
            self.assertLessEqual(v,e)
            visible_count+=bool(v);edit_count+=bool(e)
            self.assertEqual(before[offset+3],after[offset+3])
            if before[offset:offset+4]!=after[offset:offset+4]:
                changed+=1
                self.assertEqual(e,255)
                changed_outside_centre+=not v
        self.assertEqual(changed,manifest["defect"]["changed_pixels"])
        self.assertEqual(visible_count,manifest["defect"]["visible_pixel_centres"])
        self.assertEqual(edit_count,manifest["defect"]["edit_support_pixels"])
        self.assertGreater(changed_outside_centre,0)  # Declared antialias footprint, not an invented exact centre mask.
        self.assertGreater(changed,1000)

    def test_untrusted_json_cannot_turn_an_archive_into_reload_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            manifest=json.loads((FIXTURE/"manifestfixture.json").read_bytes())
            manifest["human_reviewed"]=True
            (root/"manifestfixture.json").write_text(json.dumps(manifest),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"manifest changed"):
                verify_fixture(root)

    def test_asset_corruption_is_rejected_before_any_proof_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/"fixture"
            shutil.copytree(FIXTURE,root)
            (root/"original-reference.glb").write_bytes(b"not the accepted source GLB")
            with self.assertRaisesRegex(ValueError,"frozen byte fingerprint"):
                verify_fixture(root)

    @unittest.skipUnless(os.environ.get("MESHVENN_TEST_BLENDER"),"Set MESHVENN_TEST_BLENDER for an actual fresh-process GLB reload.")
    def test_exact_source_glb_reloads_in_a_fresh_blender_process_without_mutation(self):
        before=hashlib.sha256((FIXTURE/"original-reference.glb").read_bytes()).hexdigest()
        process=subprocess.run([os.environ["MESHVENN_TEST_BLENDER"],"--background","--factory-startup","--python-exit-code","1",
            "--python",str(ROOT/"scripts/build_diagnostic_reference.py"),"--","--output",str(FIXTURE),"--verify-glb-only"],
            capture_output=True,text=True,timeout=90)
        self.assertEqual(process.returncode,0,process.stdout[-4000:]+process.stderr[-4000:])
        self.assertIn("GLB_RELOAD_VERIFIED "+before,process.stdout)
        self.assertEqual(hashlib.sha256((FIXTURE/"original-reference.glb").read_bytes()).hexdigest(),before)


if __name__=="__main__":unittest.main()
