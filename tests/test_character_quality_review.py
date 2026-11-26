"""Tampering, framing and human-provenance checks for the review adapter.

Tiny files below test presentation contracts, not reconstruction quality.
Actual exported robot GLBs are exercised separately by the Blender pipeline.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.character_quality.presentation import write_presentation
from scripts.character_quality.render import render_comparison
from scripts.character_quality.review import review_template,validate_review


def specimen(root):
    def record(path,data):
        full=root/path;full.parent.mkdir(parents=True,exist_ok=True);full.write_bytes(data)
        return {"path":path,"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data)}
    assets=[]
    for role in ("source","candidate","reference"):
        glb=record(role+".glb",b"contract fixture "+role.encode())
        mesh=record(role+".json",b'{"vertices":[],"triangles":[]}')
        frame=dict(record(role+".png",b"PNG contract fixture"),mode="flat",crop="full",angle=45,
                   camera={"location":[2,-2,0],"target":[0,0,0],"ortho_scale":2.3})
        assets.append({"asset_id":role,"role":role,"label":role,"glb":glb,"mesh":mesh,"frames":[frame],
                       "reload":{"verified":True,"source_glb_sha256":glb["sha256"]}})
    return {"schema_version":1,"status":"completed","output_root":str(root),"request_sha256":"a"*64,
            "angles":[45],"modes":["flat"],"assets":assets}


class RenderInputGuards(unittest.TestCase):
    def test_wrong_glb_hash_cannot_launch_blender_or_stage_a_substitute(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);glb=root/"real.glb";glb.write_bytes(b"actual supplied bytes")
            asset={"asset_id":"source","role":"source","label":"Source","glb_path":str(glb),"glb_sha256":"0"*64}
            with patch("scripts.character_quality.render.subprocess.Popen") as launch:
                with self.assertRaisesRegex(ValueError,"SHA256"):
                    render_comparison([asset],root/"output",blender_executable=root/"blender")
            launch.assert_not_called()
            self.assertFalse((root/"output").exists())

    def test_reference_is_not_accepted_as_the_source(self):
        with self.assertRaisesRegex(ValueError,"Exactly one source"):
            render_comparison([{"role":"reference"}],Path("unused"),blender_executable=Path("unused"))


class PresentationIntegrity(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.manifest=specimen(self.root)

    def publish(self):
        with patch("scripts.character_quality.presentation.write_contact_sheet"):
            return write_presentation(self.manifest,self.root)

    def test_changed_download_bytes_prevent_publication(self):
        (self.root/"candidate.glb").write_bytes(b"replacement hidden behind the old label")
        with self.assertRaisesRegex(ValueError,"file changed"):self.publish()
        self.assertFalse((self.root/"index.html").exists())

    def test_per_candidate_fit_cannot_hide_changed_proportions(self):
        self.manifest["assets"][1]["frames"][0]["camera"]["ortho_scale"]=4
        with self.assertRaisesRegex(ValueError,"cameras differ"):self.publish()

    def test_partial_render_is_not_presented_as_complete(self):
        self.manifest["status"]="partial"
        with self.assertRaisesRegex(ValueError,"incomplete"):self.publish()

    def test_missing_synchronized_candidate_frame_is_rejected(self):
        self.manifest["assets"][1]["frames"]=[]
        with self.assertRaisesRegex(ValueError,"frames are missing"):self.publish()

    def test_link_cannot_escape_to_a_network_or_parent_file(self):
        for path in ("https://example.invalid/substitute.glb","../substitute.glb","C:/other.glb"):
            with self.subTest(path=path):
                changed=copy.deepcopy(self.manifest)
                changed["assets"][1]["glb"]["path"]=path
                with patch("scripts.character_quality.presentation.write_contact_sheet"):
                    with self.assertRaisesRegex(ValueError,"Unsafe package path"):
                        write_presentation(changed,self.root)

    def test_first_page_is_explicit_and_escaped_with_unknown_human_review(self):
        self.manifest["assets"][1]["label"]='Résultat </script><img src="https://example.invalid">'
        page=self.publish().read_text(encoding="utf-8")
        self.assertIn("AVANT · Source à conserver",page)
        self.assertIn("APRÈS · Résultat obtenu",page)
        self.assertIn('src="source.png"',page)
        self.assertIn('src="candidate.png"',page)
        self.assertNotIn('<img src="https://example.invalid">',page)
        self.assertIn("&lt;/script&gt;",page)
        template=json.loads((self.root/"human-review-template.json").read_text(encoding="utf-8"))
        self.assertEqual("unknown",template["status"])
        self.assertEqual(["candidate"],[r["asset_id"] for r in template["reviews"]])
        self.assertEqual(self.manifest["assets"][1]["glb"]["sha256"],template["binding"]["assets"][1]["glb_sha256"])


class HumanReviewProvenance(unittest.TestCase):
    def test_answers_never_create_automatic_quality_certification(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=specimen(Path(folder));record=review_template(manifest)
            self.assertEqual("unknown",validate_review(record,manifest)["status"])
            record["reviewer"]="reviewer-test";record["reviewed_at"]="2026-11-26T12:00:00Z"
            record["reviews"][0]["answers"]={"head_boxy":"no","bust_coherent":"yes","extremities_preserved":"yes"}
            result=validate_review(record,manifest)
            self.assertEqual("recorded",result["status"])
            self.assertEqual("unknown",result["quality_certification"])

    def test_review_of_different_glb_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=specimen(Path(folder));record=review_template(manifest)
            manifest["assets"][1]["glb"]["sha256"]="b"*64
            with self.assertRaisesRegex(ValueError,"different GLBs"):validate_review(record,manifest)


if __name__=="__main__":unittest.main()
