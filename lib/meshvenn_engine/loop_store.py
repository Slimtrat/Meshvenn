"""Durable local snapshots and immutable bytes, without application decisions.

The process owner configures the root. Callbacks run under an OS lock and must
only transform JSON; reserve dispatch here, then call a provider after update.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from .errors import EngineError

MAX_STATE_BYTES = 32 * 1024 * 1024
MAX_HISTORY_BYTES = 256 * 1024 * 1024
MAX_REVISIONS = 4096


class LoopStoreError(EngineError):
    """A storage/locking failure, separate from invalid application arguments."""


def _storage_errors(method):
    @wraps(method)
    def call(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except OSError as exc:
            raise LoopStoreError("store_unavailable", "The filesystem could not complete durable storage.") from exc
    return call


def _digest(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("An artifact/revision address must be a lowercase SHA-256 digest.")
    return value


def _json_bytes(value, limit=MAX_STATE_BYTES):
    nodes = 0
    text_bytes = 0
    def visit(item, depth):
        nonlocal nodes, text_bytes
        nodes += 1
        if nodes > 2_000_000 or depth > 64:
            raise ValueError("Loop JSON exceeds its node/depth budget.")
        kind = type(item)
        if kind is str:
            if len(item) > limit:
                raise ValueError("Loop JSON exceeds its byte budget.")
            text_bytes += len(item.encode("utf-8"))
            if text_bytes > limit:
                raise ValueError("Loop JSON exceeds its byte budget.")
        elif item is None or kind in (bool, int):
            pass
        elif kind is float and math.isfinite(item):
            pass
        elif kind is list:
            for child in item:
                visit(child, depth+1)
        elif kind is dict and all(type(key) is str for key in item):
            for key, child in item.items():
                visit(key, depth+1)
                visit(child, depth+1)
        else:
            raise ValueError("Loop state must contain only finite JSON values.")
    try:
        visit(value, 0)
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("Loop state must be finite UTF-8 JSON.") from exc
    if len(encoded) > limit:
        raise ValueError("Loop JSON exceeds its byte budget.")
    return encoded


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field.")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Nonfinite JSON number.")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LoopStoreError("store_corrupt", "Stored JSON is malformed.") from exc


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _directory(path):
    info = path.lstat()
    if _linked(info) or not stat.S_ISDIR(info.st_mode):
        raise LoopStoreError("store_corrupt", "Store directories must be real directories.")


def _sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _move(source, target, *, replace):
    if os.name == "nt":
        import ctypes
        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
        move.restype = ctypes.c_int
        # WRITE_THROUGH plus fsync on the complete temporary file. The source
        # and destination always share a directory/filesystem.
        if not move(str(source), str(target), 8 | (1 if replace else 0)):
            raise ctypes.WinError(ctypes.get_last_error())
    elif replace:
        os.replace(source, target)
    else:
        os.link(source, target)  # Fails if an immutable address already exists.


class LoopStore:
    @_storage_errors
    def __init__(self, root, *, lock_timeout=10., max_artifact_bytes=256*1024*1024):
        if (type(lock_timeout) not in (int, float) or not math.isfinite(lock_timeout) or not 0 < lock_timeout <= 120
                or type(max_artifact_bytes) is not int or not 1 <= max_artifact_bytes <= 512*1024*1024):
            raise ValueError("Store limits require a finite lock timeout and bounded artifact size.")
        self.root = Path(root).absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        _directory(self.root)
        self.root = self.root.resolve(strict=True)
        self.lock_timeout, self.max_artifact_bytes = float(lock_timeout), max_artifact_bytes
        for name in ("sessions", "locks", "artifacts"):
            path = self.root/name
            path.mkdir(mode=0o700, exist_ok=True)
            _directory(path)
        _sync_directory(self.root)

    def _session(self, session_id):
        if type(session_id) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", session_id):
            raise ValueError("Session IDs require 1-128 ASCII letters, digits, underscores or hyphens.")
        _directory(self.root)
        _directory(self.root/"sessions")
        return self.root/"sessions"/("s-"+session_id)

    @contextmanager
    def _lock(self, session_id):
        self._session(session_id)
        _directory(self.root/"locks")
        path = self.root/"locks"/("s-"+session_id+".lock")
        if path.exists() or path.is_symlink():
            if _linked(path.lstat()) or not path.is_file():
                raise LoopStoreError("store_corrupt", "Session locks must be regular files.")
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        locked = False
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise LoopStoreError("store_corrupt", "Session locks must be regular files.")
            deadline = time.monotonic()+self.lock_timeout
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if time.monotonic() >= deadline:
                        raise LoopStoreError("store_lock_timeout", "Another process holds the session lock.") from exc
                    time.sleep(min(.01, max(0.,deadline-time.monotonic())))
            yield
        finally:
            try:
                if locked:
                    if os.name == "nt":
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    @staticmethod
    def _read(path, limit, *, digest=None, retain=True):
        info = path.lstat()
        if _linked(info) or not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise LoopStoreError("store_corrupt", "Stored file type or size is invalid.")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise LoopStoreError("store_corrupt", "Stored file type or size is invalid.")
            actual, chunks, remaining = hashlib.sha256(), [], before.st_size
            while remaining:
                chunk = stream.read(min(131072,remaining))
                if not chunk:
                    raise LoopStoreError("store_corrupt", "Stored bytes changed during reading.")
                actual.update(chunk)
                if retain:
                    chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(stream.fileno())
            if stream.read(1) or (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
                raise LoopStoreError("store_corrupt", "Stored bytes changed during reading.")
            if digest is not None and actual.hexdigest() != digest:
                raise LoopStoreError("store_corrupt", "Stored content differs from its SHA-256 address.")
            return b"".join(chunks) if retain else None

    def _publish(self, path, raw, *, replace=False):
        _directory(path.parent)
        descriptor, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if replace and (path.exists() or path.is_symlink()):
                if _linked(path.lstat()) or not path.is_file():
                    raise LoopStoreError("store_corrupt", "A head pointer must be a regular file.")
            try:
                _move(temporary,path,replace=replace)
            except FileExistsError:
                if replace:
                    raise LoopStoreError("store_corrupt", "An immutable address already has different bytes.")
                self._read(path,len(raw),digest=hashlib.sha256(raw).hexdigest(),retain=False)
            _sync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _current(self, session_id):
        path = self._session(session_id)
        try:
            _directory(path)
            head = _decode(self._read(path/"head.json",1024))
        except FileNotFoundError as exc:
            raise LoopStoreError("session_not_found", "No committed session exists for this ID.") from exc
        try:
            _directory(path/"revisions")
        except FileNotFoundError as exc:
            raise LoopStoreError("store_corrupt", "The committed revision directory is missing.") from exc
        if (type(head) is not dict or set(head)!={"schema_version","revision"}
                or type(head["schema_version"]) is not int or head["schema_version"]!=1):
            raise LoopStoreError("store_corrupt", "Session head schema is invalid.")
        try:
            digest = _digest(head["revision"])
        except ValueError as exc:
            raise LoopStoreError("store_corrupt", "Session head address is invalid.") from exc
        return digest,self._revision(path,session_id,digest)

    def _revision(self, path, session_id, digest):
        try:
            raw = self._read(path/"revisions"/(digest+".json"),MAX_STATE_BYTES+1024,digest=digest)
        except FileNotFoundError as exc:
            raise LoopStoreError("store_corrupt", "Committed revision bytes are missing.") from exc
        revision = _decode(raw)
        if (type(revision) is not dict or set(revision)!={"schema_version","session_id","sequence","previous","state"}
                or type(revision["schema_version"]) is not int or revision["schema_version"]!=1
                or revision["session_id"]!=session_id or type(revision["sequence"]) is not int
                or not 0 <= revision["sequence"] < MAX_REVISIONS or type(revision["state"]) is not dict):
            raise LoopStoreError("store_corrupt", "Revision schema or session binding is invalid.")
        previous = revision["previous"]
        if (revision["sequence"]==0) != (previous is None):
            raise LoopStoreError("store_corrupt", "Revision ancestry is invalid.")
        try:
            if previous is not None:
                _digest(previous)
            _json_bytes(revision["state"])
        except ValueError as exc:
            raise LoopStoreError("store_corrupt", "Revision ancestry or state is invalid.") from exc
        return revision

    def _write_head(self, path, digest):
        self._publish(path/"head.json",_json_bytes({"schema_version":1,"revision":digest}),replace=True)

    def _commit(self, session_id, state, previous, sequence):
        if type(state) is not dict:
            raise ValueError("A loop state must be a JSON object.")
        # Snapshot before publishing; caller mutation cannot reach committed data.
        state = _decode(_json_bytes(state))
        if sequence >= MAX_REVISIONS:
            raise LoopStoreError("store_limit", "The session revision budget is exhausted.")
        revision = dict(schema_version=1,session_id=session_id,sequence=sequence,previous=previous,state=state)
        raw = _json_bytes(revision,MAX_STATE_BYTES+1024)
        digest = hashlib.sha256(raw).hexdigest()
        path = self._session(session_id)
        self._publish(path/"revisions"/(digest+".json"),raw)
        self._write_head(path,digest)
        return state

    @_storage_errors
    def create(self, session_id: str, state: dict) -> None:
        with self._lock(session_id):
            path = self._session(session_id)
            path.mkdir(mode=0o700, exist_ok=True)
            _directory(path)
            if (path/"head.json").exists() or (path/"head.json").is_symlink():
                self._current(session_id)  # Corruption is not silently replaced.
                raise LoopStoreError("session_exists", "A committed session already exists for this ID.")
            revisions = path/"revisions"
            revisions.mkdir(mode=0o700,exist_ok=True)
            _directory(revisions)
            _sync_directory(self.root/"sessions")
            _sync_directory(path)
            self._commit(session_id,state,None,0)

    @_storage_errors
    def load(self, session_id: str) -> dict:
        with self._lock(session_id):
            return self._current(session_id)[1]["state"]

    @_storage_errors
    def update(self, session_id: str, callback) -> dict:
        if not callable(callback):
            raise ValueError("A state update requires a pure JSON transformation callback.")
        with self._lock(session_id):
            digest,current = self._current(session_id)
            updated = callback(current["state"])
            return self._commit(session_id,updated,digest,current["sequence"]+1)

    @_storage_errors
    def history(self, session_id: str) -> tuple[dict, ...]:
        with self._lock(session_id):
            digest,current = self._current(session_id)
            path, result, total, sequence = self._session(session_id), [], 0, current["sequence"]
            while True:
                total += len(_json_bytes(current["state"]))
                if total > MAX_HISTORY_BYTES:
                    raise LoopStoreError("store_limit", "History exceeds its 256 MiB serialized-state budget.")
                if current["sequence"]!=sequence:
                    raise LoopStoreError("store_corrupt", "Revision history is not contiguous.")
                result.append(current["state"])
                if current["previous"] is None:
                    return tuple(reversed(result))
                sequence -= 1
                current = self._revision(path,session_id,current["previous"])

    def _artifact(self, digest, *, create=False):
        digest = _digest(digest)
        _directory(self.root)
        _directory(self.root/"artifacts")
        folder = self.root/"artifacts"/digest[:2]
        if create:
            folder.mkdir(mode=0o700,exist_ok=True)
            _sync_directory(folder.parent)
        _directory(folder)
        return folder/digest

    @_storage_errors
    def put_artifact(self, data: bytes, expected_sha256=None) -> str:
        if type(data) is not bytes or len(data)>self.max_artifact_bytes:
            raise ValueError("Artifacts require immutable bytes within the configured size budget.")
        digest = hashlib.sha256(data).hexdigest()
        if expected_sha256 is not None and _digest(expected_sha256)!=digest:
            raise ValueError("Artifact bytes do not match the expected SHA-256 digest.")
        path = self._artifact(digest,create=True)
        if path.exists() or path.is_symlink():
            self._read(path,self.max_artifact_bytes,digest=digest,retain=False)
        else:
            self._publish(path,data)
        return digest

    @_storage_errors
    def read_artifact(self, sha256: str) -> bytes:
        try:
            return self._read(self._artifact(sha256),self.max_artifact_bytes,digest=sha256)
        except FileNotFoundError as exc:
            raise LoopStoreError("artifact_not_found", "The requested artifact is absent.") from exc

    @_storage_errors
    def has_artifact(self, sha256: str) -> bool:
        try:
            self._read(self._artifact(sha256),self.max_artifact_bytes,digest=sha256,retain=False)
            return True
        except FileNotFoundError:
            return False
