"""Fake ports qualify gateway behavior only, never geometric reconstruction."""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from meshvenn_agent import ArtifactStore, Gateway, GatewayError, GatewayLimits
from meshvenn_agent.contracts import ACTIONS, decode_json


class PortError(Exception):
    def __init__(self, code, message, details=None):
        self.code, self.message, self.details = code, message, details or {}


class FakeEngine:
    """An adapter fixture; its PASS is not native qualification evidence."""
    def __init__(self, value=None):
        self.value = value if value is not None else {"report": {"completion": "complete", "findings": []},
                                                     "verification_status": "unknown"}
        self.calls = []
        self.available = True
        self.error = None

    def capabilities(self):
        return dict(schema_version=1, engine_version="adapter-test-only", actions={name:
            dict(version=1, available=self.available, reason="" if self.available else "fixture unavailable",
                 input_schema={"type": "object"}, output_schema={"type": "object"}) for name in ACTIONS})

    def execute(self, action, arguments, *, cancel=None):
        self.calls.append((action, arguments, cancel))
        if self.error:
            raise self.error
        if action == "engine.capabilities":
            return self.capabilities()
        return self.value


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ArtifactStore(self.temporary.name)
        self.engine = FakeEngine()
        self.gateway = Gateway(self.engine, self.store)
        self.arguments = {"view_set": {}, "inputs": {}}

    def test_import_does_not_load_engine_blender_or_mcp(self):
        source = "import sys,meshvenn_agent;assert not any(k=='bpy' or k=='mcp' or k=='meshvenn_engine' or k=='core' for k in sys.modules)"
        completed = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_catalogue_versions_schemas_annotations_and_unavailable(self):
        catalogue = self.gateway.catalogue()
        self.assertEqual(catalogue["schema_version"], 1)
        self.assertEqual({item["name"] for item in catalogue["actions"]}, set(ACTIONS))
        self.assertTrue(all(item["version"] == 1 and "input_schema" in item and not item["annotations"]["technicalCompletionIsVerification"] for item in catalogue["actions"]))
        self.engine.available = False
        result = self.gateway.execute("geometry.diagnose", self.arguments)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["verification_status"], "unknown")
        self.assertEqual(self.engine.calls, [])

    def test_technical_success_preserves_engine_fail_or_unknown_without_inference(self):
        for verification in ("fail", "unknown", "not_applicable", "pass"):
            with self.subTest(verification=verification):
                self.engine.value["verification_status"] = verification
                result = self.gateway.execute("geometry.diagnose", self.arguments, request_id="request-1")
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["technical_status"], "completed")
                self.assertEqual(result["verification_status"], verification)
        del self.engine.value["verification_status"]
        self.assertEqual(self.gateway.execute("geometry.diagnose", self.arguments)["verification_status"], "unknown")

    def test_mesh_completion_cannot_claim_geometric_pass(self):
        self.engine.value = {"mesh": {"vertex_count": 8}, "verification_status": "unknown"}
        result = self.gateway.execute("geometry.mesh", {"volume": {}})
        self.assertEqual((result["status"], result["verification_status"]), ("completed", "unknown"))
        self.engine.value["verification_status"] = "pass"
        result = self.gateway.execute("geometry.mesh", {"volume": {}})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "invalid_engine_output")

    def test_incomplete_report_cannot_be_presented_as_pass(self):
        self.engine.value = {"report": {"completion": "partial"}, "verification_status": "pass"}
        result = self.gateway.execute("geometry.diagnose", self.arguments)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["verification_status"], "unknown")

    def test_unknown_action_extra_arguments_and_host_overrides_reject_before_port(self):
        cases = [("shell.execute", {"code": "ignored"}), ("geometry.diagnose", {**self.arguments, "python_executable": "x"}),
                 ("geometry.diagnose", {**self.arguments, "policy": {"backend": "x"}}),
                 ("views.preflight", {**self.arguments, "inputs": {"v": {"image": {"path": "image.png"}}}})]
        for action, arguments in cases:
            with self.subTest(action=action):
                result = self.gateway.execute(action, arguments)
                self.assertEqual(result["status"], "invalid_request")
        self.assertEqual(self.engine.calls, [])

    def test_strict_envelope_json_duplicate_nonfinite_types_versions_limits(self):
        valid = dict(schema_version=1, request_id="strict", action="geometry.diagnose", action_version=1, arguments=self.arguments)
        for changes in ({"schema_version": True}, {"action_version": 2}, {"request_id": "../path"}, {"extra": 1}, {"arguments": []}):
            self.assertEqual(self.gateway.invoke({**valid, **changes})["status"], "invalid_request")
        for raw in ('{"action":1,"action":2}', '{"value":NaN}', '{"value":1e999}', b"\xff"):
            self.assertEqual(self.gateway.invoke_json(raw)["status"], "invalid_request")
        for argument in (float("nan"), (1, 2), {1: "not JSON key"}):
            self.assertEqual(self.gateway.execute("geometry.mesh", {"volume": argument})["status"], "invalid_request")
        limited = Gateway(self.engine, self.store, limits=GatewayLimits(max_request_bytes=64))
        self.assertEqual(limited.execute("geometry.diagnose", self.arguments)["status"], "invalid_request")

    def test_large_response_saved_losslessly_report_and_summary_bounded(self):
        self.engine.value = dict(report={"report_id": "original", "completion": "complete", "findings":
             [{"status": "unknown", "message": "detail" * 100} for _ in range(100)]},
             verification_status="unknown", data="original-pixels" * 3000)
        result = self.gateway.execute("geometry.diagnose", self.arguments)
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["result"])
        self.assertIsNone(result["report"])
        self.assertEqual(result["summary"]["report"]["finding_count"], 100)
        ref = result["artifact"]
        self.assertEqual(ref["media_type"], "application/json")
        payload, offset = bytearray(), 0
        while True:
            chunk = self.gateway.read_artifact(ref["sha256"], offset=offset, limit=1024)
            self.assertEqual(chunk["status"], "completed")
            payload.extend(base64.b64decode(chunk["data_base64"]))
            offset = chunk["next_offset"]
            if chunk["eof"]:
                break
        self.assertEqual(json.loads(payload), self.engine.value)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), ref["sha256"])
        self.assertEqual(len(payload), ref["bytes"])

    def test_engine_output_and_artifact_limits_are_enforced(self):
        gateway = Gateway(self.engine, self.store, limits=GatewayLimits(max_response_bytes=2048,
                           max_inline_bytes=1024, max_report_bytes=1024))
        self.engine.value = {"data": "x" * 4096}
        self.assertEqual(gateway.execute("geometry.diagnose", self.arguments)["error"]["code"], "invalid_engine_output")
        gateway = Gateway(self.engine, self.store, limits=GatewayLimits(max_artifact_bytes=1024))
        self.assertEqual(gateway.execute("geometry.diagnose", self.arguments)["error"]["code"], "artifact_too_large")
        self.engine.value = {"data": float("inf")}
        self.assertEqual(self.gateway.execute("geometry.diagnose", self.arguments)["status"], "failed")

    def test_stale_source_error_is_preserved_and_never_becomes_success(self):
        self.engine.error = PortError("stale_source", "Original source digest changed.", {"view_id": "front"})
        result = self.gateway.execute("geometry.diagnose", self.arguments)
        self.assertEqual(result["status"], "invalid_request")
        self.assertEqual(result["error"]["code"], "stale_source")
        self.assertEqual(result["error"]["details"], {"view_id": "front"})
        self.assertIsNone(result["artifact"])

    def test_cancel_before_port_and_after_partial_return_preserve_evidence(self):
        result = self.gateway.execute("geometry.diagnose", self.arguments, cancel=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(self.engine.calls, [])
        event = {"cancel": False}
        original_execute = self.engine.execute
        def execute(*args, **kwargs):
            event["cancel"] = True
            self.engine.value = {"report": {"completion": "cancelled", "findings": []},
                                 "attempts": [{"volume": {"retained": True}}], "verification_status": "unknown"}
            return original_execute(*args, **kwargs)
        self.engine.execute = execute
        result = self.gateway.execute("geometry.diagnose", self.arguments, cancel=lambda: event["cancel"])
        self.assertEqual((result["status"], result["technical_status"]), ("cancelled", "cancelled"))
        self.assertIsNotNone(result["artifact"])
        self.assertEqual(result["report"]["completion"], "cancelled")
        self.assertEqual(result["verification_status"], "unknown")
        self.assertIsNotNone(self.engine.calls[0][2])


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ArtifactStore(self.temporary.name)

    def test_atomic_dedup_never_overwrites_accepted_bytes(self):
        data = b"original accepted data"
        first = self.store.put_bytes(data)
        path = self.store.root / first.sha256[:2] / first.sha256
        modified = path.stat().st_mtime_ns
        with patch("meshvenn_agent.artifacts.os.rename", side_effect=AssertionError("must not overwrite")), \
             patch("meshvenn_agent.artifacts.os.link", side_effect=AssertionError("must not overwrite")):
            second = self.store.put_bytes(data)
        self.assertEqual(first, second)
        self.assertEqual(path.stat().st_mtime_ns, modified)
        self.assertFalse(list(self.store.root.rglob(".pending-*")))

    def test_concurrent_publication_keeps_one_complete_address(self):
        data = b"shared immutable result" * 1024
        with ThreadPoolExecutor(max_workers=8) as workers:
            references = list(workers.map(lambda _: self.store.put_bytes(data), range(24)))
        self.assertEqual(len({ref.sha256 for ref in references}), 1)
        result = self.store.read(references[0].sha256)
        self.assertEqual(base64.b64decode(result["data_base64"]), data)
        self.assertFalse(list(self.store.root.rglob(".pending-*")))

    def test_corruption_rejects_reads_and_publication_does_not_repair_in_place(self):
        ref = self.store.put_bytes(b"original")
        path = self.store.root / ref.sha256[:2] / ref.sha256
        path.write_bytes(b"modified")
        for action in (lambda: self.store.read(ref.sha256), lambda: self.store.put_bytes(b"original")):
            with self.assertRaises(GatewayError) as context:
                action()
            self.assertEqual(context.exception.code, "artifact_integrity_error")
        self.assertEqual(path.read_bytes(), b"modified")

    def test_reads_reject_traversal_nonfinite_or_unbounded_offsets(self):
        ref = self.store.put_bytes(b"valid")
        for digest in ("../secret", ref.uri, ref.sha256.upper(), "a" * 63):
            with self.assertRaises(GatewayError):
                self.store.read(digest)
        for kwargs in ({"offset": True}, {"offset": -1}, {"offset": 6}, {"limit": True}, {"limit": 65537}):
            with self.assertRaises(GatewayError):
                self.store.read(ref.sha256, **kwargs)

    def test_observed_unsafe_links_are_rejected(self):
        ref = self.store.put_bytes(b"outside content")
        path = self.store.root / ref.sha256[:2] / ref.sha256
        outside = Path(self.temporary.name) / "outside.bin"
        outside.write_bytes(b"outside content")
        path.unlink()
        try:
            path.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"Symlink creation not permitted by this host: {exc}")
        with self.assertRaises(GatewayError) as context:
            self.store.read(ref.sha256)
        self.assertEqual(context.exception.code, "unsafe_artifact_path")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO is a POSIX-only file type.")
    def test_nonregular_artifact_is_rejected_before_blocking_open(self):
        ref = self.store.put_bytes(b"fifo address")
        path = self.store.root / ref.sha256[:2] / ref.sha256
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(GatewayError):
            self.store.read(ref.sha256)


if __name__ == "__main__":
    unittest.main()
