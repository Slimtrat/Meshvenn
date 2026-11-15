"""Real process locks, crash recovery and byte-preserving durable storage."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"lib"))
from meshvenn_engine.loop_store import LoopStore, LoopStoreError, MAX_STATE_BYTES


def concurrent_updates(root, marker, queue):
    try:
        store = LoopStore(root)
        for index in range(12):
            def append(state):
                return {"count":state["count"]+1,"events":[*state["events"],f"{marker}-{index}"]}
            store.update("shared",append)
        queue.put("ok")
    except Exception as exc:
        queue.put(repr(exc))


def hold_update(root, ready):
    store = LoopStore(root)
    def wait(state):
        ready.set()
        # Parent terminates this process while it owns the OS lock.
        multiprocessing.Event().wait(30)
        return {"committed":True}
    store.update("shared",wait)


def crash_before_head(root):
    store = LoopStore(root)
    store._write_head = lambda *args: os._exit(23)
    store.update("shared",lambda state:{"count":state["count"]+1})


def concurrent_artifact(root, barrier, queue):
    try:
        store = LoopStore(root)
        publish = store._publish
        def synchronized(path, raw, **kwargs):
            barrier.wait(8)  # Both observed absence before attempting publication.
            publish(path,raw,**kwargs)
        store._publish = synchronized
        queue.put(store.put_artifact(glb_bytes()))
    except Exception as exc:
        queue.put(repr(exc))


def glb_bytes():
    text = b'{"asset":{"version":"2.0"},"buffers":[{"byteLength":4}]}'
    text += b" "*((-len(text))%4)
    body = struct.pack("<I4s",len(text),b"JSON")+text+struct.pack("<I4s",4,b"BIN\0")+b"\x00\xff\x80\x01"
    return struct.pack("<4sII",b"glTF",2,12+len(body))+body


class LoopStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = LoopStore(self.root)

    def code(self, code, callback):
        with self.assertRaises(LoopStoreError) as caught:
            callback()
        self.assertEqual(caught.exception.code,code)

    def test_restart_history_and_returned_snapshots_are_independent(self):
        original = {"phase":"new","events":[{"id":1}]}
        self.assertIsNone(self.store.create("CON",original))  # Portable prefixed on disk.
        original["events"].clear()
        loaded = LoopStore(self.root).load("CON")
        loaded["events"][0]["id"] = 99
        changed = self.store.update("CON",lambda state:{**state,"phase":"reserved"})
        changed["events"].clear()
        self.assertEqual(LoopStore(self.root).history("CON"),(
            {"phase":"new","events":[{"id":1}]},{"phase":"reserved","events":[{"id":1}]}))
        self.code("session_exists",lambda:self.store.create("CON",{}))
        self.code("session_not_found",lambda:self.store.load("absent"))

    def test_callback_failure_and_invalid_result_leave_head_unchanged(self):
        self.store.create("shared",{"count":0})
        def failed(state):
            state["count"] = 100
            raise RuntimeError("Pure transition rejected.")
        with self.assertRaisesRegex(RuntimeError,"transition"):
            self.store.update("shared",failed)
        for callback in (lambda state:None,lambda state:{"bad":float("nan")},lambda state:{"tuple":(1,2)}):
            with self.assertRaises(ValueError):
                self.store.update("shared",callback)
        self.assertEqual(self.store.load("shared"),{"count":0})
        self.assertEqual(len(self.store.history("shared")),1)

    def test_two_processes_update_under_one_read_modify_commit_lock(self):
        self.store.create("shared",{"count":0,"events":[]})
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        self.addCleanup(queue.close)
        processes = [context.Process(target=concurrent_updates,args=(str(self.root),name,queue)) for name in ("a","b")]
        for process in processes:
            process.start()
            self.addCleanup(self.stop,process)
        for process in processes:
            process.join(15)
            self.assertEqual(process.exitcode,0)
        self.assertEqual([queue.get(timeout=2),queue.get(timeout=2)],["ok","ok"])
        result = self.store.load("shared")
        self.assertEqual(result["count"],24)
        self.assertEqual(len(set(result["events"])),24)
        self.assertEqual(tuple(s["count"] for s in self.store.history("shared")),tuple(range(25)))

    @staticmethod
    def stop(process):
        if process.is_alive():
            process.terminate()
        process.join(3)

    def test_lock_timeout_and_process_termination_release_os_lock(self):
        self.store.create("shared",{"count":0})
        context = multiprocessing.get_context("spawn")
        ready = context.Event()
        child = context.Process(target=hold_update,args=(str(self.root),ready))
        child.start()
        self.addCleanup(self.stop,child)
        self.assertTrue(ready.wait(8))
        contender = LoopStore(self.root,lock_timeout=.05)
        self.code("store_lock_timeout",lambda:contender.update("shared",lambda state:state))
        self.stop(child)
        self.assertEqual(contender.update("shared",lambda state:{"count":1}),{"count":1})
        self.assertEqual(len(contender.history("shared")),2)

    def test_actual_crash_after_revision_before_head_preserves_old_commit_and_redo(self):
        self.store.create("shared",{"count":0})
        context = multiprocessing.get_context("spawn")
        child = context.Process(target=crash_before_head,args=(str(self.root),))
        child.start()
        self.addCleanup(self.stop,child)
        child.join(8)
        self.assertEqual(child.exitcode,23)
        resumed = LoopStore(self.root)
        self.assertEqual(resumed.load("shared"),{"count":0})
        self.assertEqual(resumed.history("shared"),({"count":0},))
        self.assertEqual(len(tuple((self.root/"sessions/s-shared/revisions").glob("*.json"))),2)
        resumed.update("shared",lambda state:{"count":state["count"]+1})
        self.assertEqual(resumed.history("shared"),({"count":0},{"count":1}))

    def test_glb_bytes_are_verified_immutable_and_reused_across_restart(self):
        content = glb_bytes()
        digest = hashlib.sha256(content).hexdigest()
        self.assertEqual(self.store.put_artifact(content,expected_sha256=digest),digest)
        path = self.root/"artifacts"/digest[:2]/digest
        before = path.stat().st_mtime_ns
        self.assertEqual(LoopStore(self.root).put_artifact(content),digest)
        self.assertEqual(path.stat().st_mtime_ns,before)
        self.assertEqual(self.store.read_artifact(digest),content)
        self.assertTrue(self.store.has_artifact(digest))
        self.assertFalse(self.store.has_artifact("f"*64))
        self.code("artifact_not_found",lambda:self.store.read_artifact("f"*64))
        with self.assertRaises(ValueError):
            self.store.put_artifact(content,expected_sha256="0"*64)
        path.write_bytes(b"corrupted")
        for operation in (lambda:self.store.read_artifact(digest),lambda:self.store.has_artifact(digest),
                          lambda:self.store.put_artifact(content)):
            self.code("store_corrupt",operation)
        self.assertEqual(path.read_bytes(),b"corrupted")  # Never repair accepted bytes in place.

    def test_two_processes_publish_one_complete_immutable_artifact(self):
        context = multiprocessing.get_context("spawn")
        barrier,queue = context.Barrier(2),context.Queue()
        self.addCleanup(queue.close)
        processes = [context.Process(target=concurrent_artifact,args=(str(self.root),barrier,queue)) for _ in range(2)]
        for process in processes:
            process.start()
            self.addCleanup(self.stop,process)
        for process in processes:
            process.join(12)
            self.assertEqual(process.exitcode,0)
        digest = hashlib.sha256(glb_bytes()).hexdigest()
        self.assertEqual([queue.get(timeout=2),queue.get(timeout=2)],[digest,digest])
        self.assertEqual(self.store.read_artifact(digest),glb_bytes())

    def test_corrupt_head_and_revision_are_rejected(self):
        self.store.create("shared",{"count":0})
        head = self.root/"sessions/s-shared/head.json"
        original = head.read_bytes()
        head.write_bytes(b'{"revision":')
        self.code("store_corrupt",lambda:self.store.load("shared"))
        self.code("store_corrupt",lambda:self.store.create("shared",{}))
        head.write_bytes(original)
        digest = json.loads(original)["revision"]
        revision = head.parent/"revisions"/(digest+".json")
        revision.write_bytes(b"{}")
        self.code("store_corrupt",lambda:self.store.load("shared"))

    def test_ids_nonjson_and_budgets_fail_without_a_commit(self):
        for identifier in ("../escape","a/b","a:b","a.","",True,"x"*129):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                self.store.create(identifier,{})
        for state in ([],{"nan":float("nan")},{"object":object()},{1:"not a JSON key"}):
            with self.assertRaises(ValueError):
                self.store.create("invalid",state)
        with self.assertRaises(ValueError):
            self.store.create("oversized",{"blob":"x"*MAX_STATE_BYTES})
        self.code("session_not_found",lambda:self.store.load("oversized"))
        tiny = LoopStore(self.root,max_artifact_bytes=3)
        with self.assertRaises(ValueError):
            tiny.put_artifact(b"four")

    def test_observed_symlink_artifact_is_rejected(self):
        content = b"accepted opaque bytes"
        digest = hashlib.sha256(content).hexdigest()
        external = self.root/"outside"
        external.write_bytes(content)
        folder = self.root/"artifacts"/digest[:2]
        folder.mkdir()
        try:
            (folder/digest).symlink_to(external)
        except OSError as exc:
            self.skipTest(f"Host cannot create symlinks: {exc}")
        self.code("store_corrupt",lambda:self.store.read_artifact(digest))
        self.code("store_corrupt",lambda:self.store.put_artifact(content))


if __name__ == "__main__":
    unittest.main()
