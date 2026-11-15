"""Independent frozen definitions, not simulated provider quality claims."""
from pathlib import Path
import json
import struct
import tempfile
import unittest

from scripts.correction_loop_corpus.fixtures import build_corpus
from scripts.correction_loop_corpus.integrity import load_manifest
from scripts.correction_loop_corpus.scoring import score_case

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

    def test_no_output_cannot_satisfy_any_frozen_case(self):
        manifest,_=load_manifest(CORPUS)
        for case in manifest["cases"]:
            self.assertFalse(score_case(case,{})["passed"],case["case_id"])

    def test_real_D2_D4_improves_visible_colour_without_certifying_identity(self):
        from scripts.correction_loop_corpus.real_evidence import initialize_real_source,evaluate_real_candidate
        source=initialize_real_source()
        candidate=evaluate_real_candidate(source)
        self.assertTrue(candidate["numeric_improved"])
        self.assertEqual("pass",candidate["preflight"].report.verification_status)
        self.assertEqual("unknown",candidate["appearance"].report.verification_status)
        self.assertEqual("unknown",candidate["identity_status"])
        self.assertFalse(candidate["provider_fidelity_qualified"])

    def test_a_higher_mean_cannot_hide_a_required_failed_part(self):
        manifest,_=load_manifest(CORPUS)
        case=next(c for c in manifest["cases"] if c["case_id"]=="higher_mean_erased_part_rejected")
        record={"facts":{"runtime_state_observed":True,"baseline_mean_iou":.8,
            "evaluations":[{"candidate_sha256":"candidate","event_index":1,"mean_iou":.98,
                "all_required_pass":False,"checks":[{"code":"geometry.important_part","status":"fail","required":True}]}],
            "promotions":[{"candidate_sha256":"candidate","event_index":2}],"final":{"promoted":True}}}
        scored=score_case(case,record)
        self.assertIn("never_promote_before_global_evaluation",scored["failures"])
        self.assertIn("not_promoted",scored["failures"])


class LoopRuntimeCorpusControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch=(ROOT/"tmp").resolve()
        if not cls.scratch.is_relative_to(ROOT.resolve()):
            raise ValueError("Test scratch escaped its workspace")
        cls.scratch.mkdir(exist_ok=True)

    def test_actual_durable_runtime_promotes_only_the_passing_contract(self):
        from scripts.correction_loop_corpus.harness import execute_case
        manifest,_=load_manifest(CORPUS)
        for identifier in ("globally_improved_promoted","required_unknown_never_passes"):
            case=next(c for c in manifest["cases"] if c["case_id"]==identifier)
            with tempfile.TemporaryDirectory(prefix="d6-",dir=self.scratch) as folder:
                record=execute_case(CORPUS,case,manifest,Path(folder)/"run"/identifier)
                self.assertTrue(score_case(case,record)["passed"])
                self.assertEqual(identifier=="globally_improved_promoted",record["facts"]["final"]["promoted"])
                self.assertFalse(record["provider_fidelity_qualified"])

    def test_actual_pending_journal_restarts_without_submitting_again(self):
        from scripts.correction_loop_corpus.harness import execute_case
        manifest,_=load_manifest(CORPUS)
        case=next(c for c in manifest["cases"] if c["case_id"]=="crash_pending_resume_uncertain")
        with tempfile.TemporaryDirectory(prefix="d6-",dir=self.scratch) as folder:
            record=execute_case(CORPUS,case,manifest,Path(folder)/"run"/case["case_id"])
            self.assertTrue(score_case(case,record)["passed"])
            self.assertEqual(1,len(record["facts"]["provider_calls"]))
            self.assertEqual(0,record["facts"]["provider_calls_after_restart"])
            self.assertTrue(record["facts"]["final"]["cost_uncertain"])


if __name__=="__main__":
    unittest.main()
