"""Failure injection for orchestration/evidence integrity, not algorithm mirrors."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.diagnostic_qualification import corpora
from scripts.diagnostic_qualification.integrity import (file_record,inventory_tree,native_path,read_json,
    sha256_file,verify_file,verify_inventory)


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True),encoding="utf-8")


class CorpusExecutionFailures(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix="dq-")
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.repo=self.root/"repo";self.repo.mkdir()
        script=self.repo/"scripts/fake_runner.py"
        script.parent.mkdir();script.write_text("# Local failure injection specimen only\n",encoding="utf-8")
        self.spec=corpora.CorpusSpec("D2","fake_runner.py","test","cases")
        self.fixture=self.repo/"tests/fixtures/diagnostics/test/manifest.json"
        write_json(self.fixture,{"corpus_version":"test-contract-only","cases":[
            {"case_id":"one","split":"heldout","variants":[{"resolution":128}]}]})
        self.output=self.root/"output"

    def emit(self,command,stdout,stderr,timeout):
        """A tiny output-contract fixture, never diagnostic quality evidence."""
        stdout.write_bytes(b"injected runner\n");stderr.write_bytes(b"")
        directory=Path(command[command.index("--output")+1])
        report={"findings":[{"code":"contract.unobserved","status":"unknown"}]}
        row={"case_id":"one","split":"heldout","resolution":128,"report":"one/128/diagnostic-report.json",
             "scoring":{"passed_expectations":True},"evidence":[],"policy":{"configuration_sha256":"a"*64}}
        write_json(directory/row["report"],report)
        write_json(directory/"one/128/observations.json",row)
        summary={"schema_version":1,"qualification_status":"pass","complete_matrix":True,
                 "manifest_sha256":sha256_file(self.fixture),"implementation":{"source_sha256":{"test":"b"*64}},
                 "implementation_sources_unchanged_during_run":True,"cases":[row],"metrics":{"evaluated_variants":1}}
        write_json(directory/"qualification.json",summary)
        return {"exit_code":0,"timed_out":False,"elapsed_seconds":.01}

    def run_one(self,invoke=None):
        with patch.object(corpora,"_ROOT",self.repo),patch.object(corpora,"_SPECS",(self.spec,)), \
                patch.object(corpora,"_invoke",side_effect=invoke or self.emit):
            return corpora.run_corpora(self.output)

    def test_preserves_unknowns_and_exposed_heldout_without_global_certification(self):
        result=self.run_one()
        self.assertTrue(result["selected_full_matrices_passed"])
        self.assertEqual("unknown",result["verification_status"])
        stage=result["results"][0]
        self.assertEqual(1,stage["unknowns"]["by_code"]["contract.unobserved"])
        self.assertEqual("regression_exposed",stage["by_split"]["heldout"]["exposure"])
        self.assertFalse(Path(stage["outputs"]["summary"]).is_absolute())

    def test_subprocess_failure_cannot_reuse_a_passing_summary(self):
        def failed(*args):
            value=self.emit(*args);value["exit_code"]=7;return value
        result=self.run_one(failed)
        self.assertEqual("unknown",result["status"])
        self.assertEqual("failed",result["results"][0]["technical_status"])
        self.assertFalse(result["selected_full_matrices_passed"])
        self.assertIn("exit_status_mismatch",[i["code"] for i in result["results"][0]["issues"]])

    def test_malformed_json_is_retained_but_never_counted_as_a_pass(self):
        def malformed(*args):
            value=self.emit(*args)
            directory=Path(args[0][args[0].index("--output")+1])
            (directory/"qualification.json").write_text('{"qualification_status":"pass",',encoding="utf-8")
            return value
        result=self.run_one(malformed)
        self.assertEqual("unknown",result["results"][0]["status"])
        summary=self.output/result["results"][0]["outputs"]["summary"]
        self.assertTrue(summary.is_file())

    def test_missing_raw_archive_prevents_qualification(self):
        def missing(*args):
            value=self.emit(*args)
            directory=Path(args[0][args[0].index("--output")+1])
            (directory/"one/128/observations.json").unlink()
            return value
        result=self.run_one(missing)
        self.assertEqual("unknown",result["status"])
        self.assertIn("unverifiable_corpus_result",[i["code"] for i in result["results"][0]["issues"]])

    def test_fully_failed_matrix_retains_fail_when_raw_archive_is_missing(self):
        def failed_missing(*args):
            execution=self.emit(*args)
            directory=Path(args[0][args[0].index("--output")+1])
            summary=read_json(directory/"qualification.json")
            summary["qualification_status"]="fail"
            summary["cases"][0]["scoring"]["passed_expectations"]=False
            summary["metrics"]={"evaluated_variants":1,"failed_cases":1}
            write_json(directory/"qualification.json",summary)
            (directory/"one/128/observations.json").unlink()
            execution["exit_code"]=1
            return execution
        result=self.run_one(failed_missing)
        stage=result["results"][0]
        self.assertEqual("fail",result["status"])
        self.assertEqual("fail",stage["status"])
        self.assertEqual("fail",stage["runner_status"])
        self.assertEqual("failed",stage["technical_status"])
        self.assertTrue(stage["complete_matrix"])
        self.assertEqual(1,stage["metrics"]["failed_cases"])
        self.assertEqual(1,stage["by_split"]["heldout"]["failed"])
        self.assertEqual("one",stage["failures"][0]["case_id"])
        self.assertFalse(result["selected_full_matrices_passed"])
        self.assertIn("unverifiable_corpus_result",[i["code"] for i in stage["issues"]])

    def test_claimed_full_matrix_cannot_omit_a_frozen_configuration(self):
        manifest=read_json(self.fixture)
        manifest["cases"][0]["variants"].append({"resolution":256})
        write_json(self.fixture,manifest)
        result=self.run_one()
        self.assertEqual("unknown",result["status"])
        self.assertIn("missing case/configurations",str(result["results"][0]["issues"]))

    def test_native_absent_is_unknown_and_does_not_invoke_D3(self):
        self.spec=corpora.CorpusSpec("D3","fake_runner.py","test")
        with patch.object(corpora,"_ROOT",self.repo),patch.object(corpora,"_SPECS",(self.spec,)), \
                patch.object(corpora,"_invoke") as invoke:
            result=corpora.run_corpora(self.output)
        invoke.assert_not_called()
        self.assertEqual("unknown",result["status"])
        self.assertEqual("unavailable",result["results"][0]["technical_status"])

    def test_new_attempt_keeps_previous_outputs(self):
        first=self.run_one();first_path=self.output/first["results"][0]["outputs"]["summary"]
        original=first_path.read_bytes()
        second=self.run_one()
        self.assertNotEqual(first["results"][0]["outputs"]["root"],second["results"][0]["outputs"]["root"])
        self.assertEqual(original,first_path.read_bytes())


class EvidenceIntegrityFailures(unittest.TestCase):
    def test_missing_archive_and_tampering_are_detected(self):
        with tempfile.TemporaryDirectory(prefix="dq-evidence-") as folder:
            root=Path(folder);path=root/"archive.json";path.write_bytes(b"original evidence")
            record=file_record(path,root);inventory=inventory_tree(root)
            self.assertEqual("pass",verify_inventory(root,inventory)["status"])
            path.write_bytes(b"different evidence")
            self.assertEqual("fail",verify_file(root,record)["status"])
            path.unlink()
            self.assertEqual("fail",verify_inventory(root,inventory)["status"])

    def test_path_escape_cannot_be_laundered_by_a_correct_hash(self):
        with tempfile.TemporaryDirectory(prefix="dq-escape-") as folder:
            base=Path(folder);root=base/"evidence";root.mkdir()
            outside=base/"outside";outside.write_bytes(b"actual bytes")
            record={"path":"../outside","bytes":len(b"actual bytes"),"sha256":sha256_file(outside)}
            self.assertEqual("fail",verify_file(root,record)["status"])

    def test_duplicate_keys_and_nonfinite_results_are_invalid(self):
        with tempfile.TemporaryDirectory(prefix="dq-json-") as folder:
            path=Path(folder)/"result.json"
            for content in ('{"status":"pass","status":"fail"}','{"metric":NaN}'):
                path.write_text(content,encoding="utf-8")
                with self.assertRaises(ValueError):read_json(path)


@unittest.skipUnless(os.name=="nt","Windows extended output paths")
class WindowsLongOutput(unittest.TestCase):
    def test_extended_path_is_idempotent_and_supports_unc(self):
        ordinary=Path("C:/qualification/evidence")
        extended=native_path(ordinary)
        self.assertTrue(str(extended).startswith("\\\\?\\C:\\"))
        self.assertEqual(extended,native_path(extended))
        self.assertEqual("\\\\?\\UNC\\server\\share\\evidence",
                         str(native_path(Path("\\\\server\\share\\evidence"))))

    def test_real_D5_cli_keeps_deep_output_and_inventory_readable(self):
        # No simulated runner: exercise frozen D5 through its CLI. Missing DLL
        # intentionally leaves the native controls unqualified, never PASS.
        base=Path(tempfile.mkdtemp(prefix="dq-long-"))
        self.addCleanup(shutil.rmtree,native_path(base))
        output=base/("long-output-"+"a"*45)/("durable-evidence-"+"b"*45)/("retained-run-"+"c"*45)/("nested-output-"+"d"*45)
        self.assertGreater(len(str(output)),260)
        result=corpora.run_corpora(output,selection=("D5",))
        stage=result["results"][0]
        command_output=stage["command"][stage["command"].index("--output")+1]
        self.assertTrue(command_output.startswith("\\\\?\\"))
        self.assertEqual(native_path(output)/stage["outputs"]["root"],Path(command_output))
        self.assertEqual("unknown",stage["status"])
        self.assertEqual("unqualified",stage["runner_status"])
        self.assertEqual("completed",stage["technical_status"])
        self.assertEqual(0,stage["metrics"]["failed"])
        self.assertEqual(0,stage["metrics"]["execution_failures"])
        self.assertEqual(["matrix_incomplete"],[i["code"] for i in stage["issues"]])
        inventory=read_json(native_path(output)/stage["outputs"]["inventory"])
        self.assertEqual("pass",verify_inventory(Path(command_output),inventory)["status"])
        self.assertTrue(any(len(str(Path(command_output)/f["path"]))>300 for f in inventory["files"]))


if __name__=="__main__":
    unittest.main()
