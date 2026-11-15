"""Independent frozen definitions, not simulated provider quality claims."""
from pathlib import Path
import json
import struct
import tempfile
import unittest

from scripts.correction_loop_corpus.fixtures import build_corpus
from scripts.correction_loop_corpus.integrity import load_manifest

ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/"tests/fixtures/diagnostics/correction-loop-v1"


class LoopCorpusFreezeTests(unittest.TestCase):
    def test_frozen_sources_regenerate_identically_before_machine_evaluation(self):
        manifest,digest=load_manifest(CORPUS)
        self.assertEqual(18,len(manifest["cases"]))
        self.assertTrue(manifest["expectations_frozen_before_loop_evaluation"])
        with tempfile.TemporaryDirectory() as folder:
            other,other_digest=build_corpus(Path(folder))
            self.assertEqual(manifest,other)
            self.assertEqual(digest,other_digest)

    def test_labels_cannot_be_relaxed_after_measurement(self):
        manifest=json.loads((CORPUS/"manifest.json").read_bytes())
        manifest["cases"][0]["expected"]["controls"]=[]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"Frozen loop manifest changed"):
                load_manifest(path)

    def test_original_GLB_has_complete_binary_chunks(self):
        for name in ("original.glb","candidate.glb"):
            data=(CORPUS/"assets"/name).read_bytes()
            magic,version,total=struct.unpack_from("<4sII",data)
            self.assertEqual((b"glTF",2,len(data)),(magic,version,total))
            count,kind=struct.unpack_from("<I4s",data,12)
            self.assertEqual(b"JSON",kind)
            document=json.loads(data[20:20+count])
            length,kind=struct.unpack_from("<I4s",data,20+count)
            self.assertEqual(b"BIN\0",kind)
            self.assertEqual(len(data),28+count+length)
            self.assertEqual(3,document["accessors"][0]["count"])

    def test_no_mock_is_misrepresented_as_model_or_photo_qualification(self):
        manifest,_=load_manifest(CORPUS)
        self.assertFalse(manifest["provenance"]["human_reviewed"])
        self.assertFalse(manifest["provenance"]["provider_fidelity_qualified"])
        self.assertEqual(0,manifest["provenance"]["real_provider_calls"])
        real=[c for c in manifest["cases"] if c["scope"]!="orchestration-only"]
        self.assertEqual(1,len(real))
        self.assertIn("not_promoted",real[0]["expected"]["controls"])
        self.assertIn("real_identity_stays_unknown",real[0]["expected"]["controls"])


if __name__=="__main__":
    unittest.main()
