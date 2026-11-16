"""Public builder guards run before importing Blender or touching old evidence."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.diagnostic_qualification.reference import verify_fixture

ROOT=Path(__file__).resolve().parents[1]
WRAPPER=ROOT/"scripts/build_diagnostic_reference.py"
FIXTURE=ROOT/"tests/fixtures/diagnostics/provider-v1"
ARCHIVE=ROOT/"tests/fixtures/diagnostics/provider-authoring-v1/build_diagnostic_reference.py"
HISTORICAL_SHA="6eab89f7cab7d5fc059051e0ecd833dcaea220d89901536ea8c19e6620257ce9"


def frozen_bytes():
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in FIXTURE.iterdir() if path.is_file()}


class ReferenceBuilderGuardTests(unittest.TestCase):
    def call(self,*arguments):
        result=subprocess.run([sys.executable,"-I",str(WRAPPER),*map(str,arguments)],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2,result.stdout+result.stderr)
        self.assertNotIn("No module named 'bpy'",result.stderr)
        return result

    def test_no_default_output_and_existing_frozen_corpus_are_untouched(self):
        before=frozen_bytes()
        self.assertIn("--output",self.call().stderr)
        self.assertIn("NEW output directory",self.call("--output",FIXTURE).stderr)
        self.assertEqual(frozen_bytes(),before)
        self.assertTrue(verify_fixture(FIXTURE)["archived_reload_verified"])

    def test_existing_foreign_directory_and_file_are_never_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            sentinel=folder/"keep.txt"
            sentinel.write_bytes(b"original user bytes")
            self.call("--output",folder)
            self.call("--output",sentinel)
            self.assertEqual(list(folder.iterdir()),[sentinel])
            self.assertEqual(sentinel.read_bytes(),b"original user bytes")

    def test_read_only_verification_never_creates_a_missing_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            missing=root/"missing"
            self.call("--verify-glb-only","--output",missing)
            self.assertFalse(missing.exists())
            self.call("--verify-glb-only","--output",root)
            self.assertEqual(list(root.iterdir()),[])

    def test_historical_source_hash_is_separate_from_the_active_safe_wrapper(self):
        self.assertEqual(hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),HISTORICAL_SHA)
        result=verify_fixture(FIXTURE)
        author=result["authoring_source"]
        self.assertEqual(author["historical_manifest_path"],"scripts/build_diagnostic_reference.py")
        self.assertEqual(author["historical_source_sha256"],HISTORICAL_SHA)
        self.assertEqual(author["archived_path"],ARCHIVE.relative_to(ROOT).as_posix())
        self.assertNotEqual(author["active_wrapper_sha256"],HISTORICAL_SHA)
        self.assertLess(len(WRAPPER.read_text().splitlines()),70)

    def test_fresh_directory_is_reserved_exclusively_and_argv_is_restored(self):
        main=runpy.run_path(str(WRAPPER),run_name="builder_guard_unit")["main"]
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/"fresh"
            arguments=[str(WRAPPER),"--output",str(output)]
            seen=[]
            def authored(path,*,run_name):
                self.assertEqual(Path(path),ARCHIVE)
                self.assertTrue(output.is_dir())
                self.assertEqual(list(output.iterdir()),[])
                seen.append(sys.argv[:])
                (output/"manifestfixture.json").write_text("{}",encoding="utf-8")
            with patch.object(sys,"argv",arguments),patch.object(sys,"path",sys.path[:]), \
                    patch("sys.stderr",new_callable=io.StringIO),patch("runpy.run_path",side_effect=authored):
                main()
                self.assertEqual(sys.argv,arguments)
                with self.assertRaises(SystemExit) as rejected:
                    main()
                self.assertEqual(rejected.exception.code,2)
            self.assertEqual(len(seen),1)
            proof=json.loads((output/"fresh-build-wrapper.json").read_bytes())
            self.assertEqual(proof["archived_authoring_sha256"],HISTORICAL_SHA)
            self.assertEqual(proof["active_wrapper_sha256"],hashlib.sha256(WRAPPER.read_bytes()).hexdigest())


if __name__=="__main__":unittest.main()
