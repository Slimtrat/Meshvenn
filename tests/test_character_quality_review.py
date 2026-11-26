"""Tampering, framing and human-provenance checks for the review adapter.

Tiny files below test presentation contracts, not reconstruction quality.
Actual exported robot GLBs are exercised separately by the Blender pipeline.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
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

    def test_export_to_a_different_directory_is_refused_before_writing(self):
        other=self.root/"unrelated-export"
        with self.assertRaisesRegex(ValueError,"beside its audited render package"):
            write_presentation(self.manifest,other)
        self.assertFalse(other.exists())

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
        self.assertFalse(template["self_attestation"])
        self.assertIsNone(template["experience_3d"])
        self.assertEqual(["candidate"],[r["asset_id"] for r in template["reviews"]])
        self.assertEqual(self.manifest["assets"][1]["glb"]["sha256"],template["binding"]["assets"][1]["glb_sha256"])

    @unittest.skipUnless(shutil.which("node"),"Node executes the actual offline UI JavaScript")
    def test_actual_js_preserves_unsaved_answers_when_switching_and_saving(self):
        second=copy.deepcopy(self.manifest["assets"][1]);second["asset_id"]="candidate2"
        self.manifest["assets"].append(second)
        page=self.publish().read_text(encoding="utf-8")
        payload=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',page,re.S)[1])
        script=re.findall(r'<script>(.*?)</script>',page,re.S)[0]
        # Minimal DOM implements only browser interactions used here. The exact
        # generated script (not a copied save implementation) handles changes.
        harness=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const inputs=[],ids={};let downloaded=null;
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.options=[];this.value='';this.checked=false;this.textContent='';this.handlers={};if(tag==='input')inputs.push(this)}
 append(...items){for(const item of items){this.children.push(item);if(this.tag==='select'&&item.tag==='option'){this.options.push(item);item.parent=this;if(this.value==='')this.value=item.value}}}
 replaceChildren(...items){this.children=[];this.append(...items)}
 addEventListener(name,fn){this.handlers[name]=fn}
 remove(){if(this.parent)this.parent.options=this.parent.options.filter(o=>o!==this)}
 click(){}
}
for(const id of ['candidate','mode','crop','angle','anglelabel','play','source-label','candidate-label','source-image','candidate-image','source-links','candidate-links','questions','comment','reviewer','save','saved','references','attestation','data'])ids[id]=new Element(id==='candidate'||id==='mode'?'select':'div');
for(const value of ['flat','material']){const o=new Element('option');o.value=value;ids.mode.append(o)}
ids.crop.value='full';ids.angle.value='0';ids.attestation.checked=false;
for(const value of ['beginner','occasional','experienced']){const i=new Element('input');i.name='experience_3d';i.value=value}
const document={getElementById:id=>ids[id],createElement:tag=>new Element(tag),createTextNode:text=>text,getElementsByName:name=>inputs.filter(i=>i.name===name),querySelector:selector=>{const name=/name="([^"]+)"/.exec(selector)[1];return inputs.find(i=>i.name===name&&i.checked)||null}};
const context={document,console,Blob,URL:{createObjectURL:blob=>{downloaded=blob;return 'blob:local'},revokeObjectURL:()=>{}},setTimeout:()=>1,setInterval:()=>1,clearInterval:()=>{}};
ids.data.textContent=JSON.stringify(PAYLOAD);
vm.runInNewContext(SCRIPT+`
function answer(id,value){for(const input of document.getElementsByName(id))input.checked=input.value===value}
if(document.querySelector('input[name="experience_3d"]:checked')!==null)throw Error('Experience was preselected');
if($('attestation').checked)throw Error('Attestation was preselected');
answer('head_boxy','no');$('comment').value='Premier avis conservé';
$('candidate').value='candidate2';$('candidate').onchange();
answer('bust_coherent','yes');$('comment').value='Deuxième avis conservé';
$('candidate').value='candidate';$('candidate').onchange();
if($('comment').value!=='Premier avis conservé')throw Error('First comment lost');
if(document.querySelector('input[name="head_boxy"]:checked').value!=='no')throw Error('First answer lost');
$('reviewer').value='Reviewer';$('save').onclick();
if(review.status!=='unknown')throw Error('Unattested review elevated');
answer('experience_3d','occasional');$('attestation').checked=true;$('save').onclick();
if(review.quality_certification!=='unknown')throw Error('Automatic certification');
`,context);
downloaded.text().then(text=>{const result=JSON.parse(text);assert.equal(result.reviews[0].answers.head_boxy,'no');assert.equal(result.reviews[0].comment,'Premier avis conservé');assert.equal(result.reviews[1].answers.bust_coherent,'yes');assert.equal(result.reviews[1].comment,'Deuxième avis conservé');assert.equal(result.self_attestation,true);assert.equal(result.experience_3d,'occasional');assert.equal(result.quality_certification,'unknown');console.log('ACTUAL_REVIEW_JS_PASS')}).catch(e=>{console.error(e);process.exitCode=1});
'''.replace("PAYLOAD",json.dumps(payload,ensure_ascii=True)).replace("SCRIPT",json.dumps(script,ensure_ascii=True))
        path=self.root/"exercise-ui.cjs";path.write_text(harness,encoding="utf-8")
        checked=subprocess.run([shutil.which("node"),"--check",str(path)],capture_output=True,text=True,timeout=15)
        self.assertEqual(0,checked.returncode,checked.stderr)
        executed=subprocess.run([shutil.which("node"),str(path)],capture_output=True,text=True,timeout=15)
        self.assertEqual(0,executed.returncode,executed.stderr)
        self.assertIn("ACTUAL_REVIEW_JS_PASS",executed.stdout)


class HumanReviewProvenance(unittest.TestCase):
    def test_answers_never_create_automatic_quality_certification(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=specimen(Path(folder));record=review_template(manifest)
            self.assertEqual("unknown",validate_review(record,manifest)["status"])
            record["reviewer"]="reviewer-test";record["reviewed_at"]="2026-11-26T12:00:00Z"
            record["self_attestation"]=True;record["experience_3d"]="experienced"
            record["reviews"][0]["answers"]={"head_boxy":"no","bust_coherent":"yes","extremities_preserved":"yes"}
            result=validate_review(record,manifest)
            self.assertEqual("recorded",result["status"])
            self.assertEqual("unknown",result["quality_certification"])
            self.assertEqual("self_attested_unverified",result["provenance_basis"])

    def test_name_and_date_without_attestation_remain_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=specimen(Path(folder));record=review_template(manifest)
            record.update(reviewer="Name",reviewed_at="2026-11-26T12:00:00Z",experience_3d="beginner")
            self.assertEqual("unknown",validate_review(record,manifest)["status"])
            record.update(self_attestation=True,experience_3d=None)
            self.assertFalse(validate_review(record,manifest)["human_provenance_present"])

    def test_tampered_or_timezone_free_date_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=specimen(Path(folder));record=review_template(manifest)
            record.update(reviewer="Name",self_attestation=True,experience_3d="beginner")
            for value in ("yesterday","2026-02-30T12:00:00Z","2026-11-26T12:00:00","2026-11-26"):
                with self.subTest(date=value):
                    record["reviewed_at"]=value
                    with self.assertRaisesRegex(ValueError,"ISO"):validate_review(record,manifest)

    def test_review_of_different_glb_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=specimen(Path(folder));record=review_template(manifest)
            manifest["assets"][1]["glb"]["sha256"]="b"*64
            with self.assertRaisesRegex(ValueError,"different GLBs"):validate_review(record,manifest)


if __name__=="__main__":unittest.main()
