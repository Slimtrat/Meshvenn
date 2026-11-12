"""Content-addressed immutable artifacts inside a host-configured workspace."""
from __future__ import annotations

import base64
import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .contracts import GatewayError


@dataclass(frozen=True)
class ArtifactReference:
    sha256: str
    bytes: int
    media_type: str
    uri: str

    def to_dict(self):
        return dict(sha256=self.sha256, bytes=self.bytes, media_type=self.media_type, uri=self.uri)


def _unsafe_link(path: Path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


class ArtifactStore:
    def __init__(self, workspace: str | Path, *, max_artifact_bytes: int = 256*1024*1024,
                 max_chunk_bytes: int = 64*1024):
        if (type(max_artifact_bytes) is not int or not 1 <= max_artifact_bytes <= 512*1024*1024 or
                type(max_chunk_bytes) is not int or not 1 <= max_chunk_bytes <= 1024*1024):
            raise ValueError("Artifact size and read limits must fit the bounded host profile.")
        self.workspace = Path(workspace).absolute()
        self.workspace.mkdir(parents=True, exist_ok=True)
        if _unsafe_link(self.workspace) or not self.workspace.is_dir():
            raise GatewayError("unsafe_artifact_path", "The configured workspace must be a real directory.")
        self.workspace = self.workspace.resolve(strict=True)
        self.root = self.workspace / "artifacts"
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.max_artifact_bytes, self.max_chunk_bytes = max_artifact_bytes, max_chunk_bytes
        self._check_directory(self.root)

    def _check_directory(self, directory):
        if _unsafe_link(directory) or not directory.is_dir() or directory.resolve(strict=True) != directory:
            raise GatewayError("unsafe_artifact_path", "Artifact directories must not contain links or reparse points.")
        if directory != self.workspace and not directory.is_relative_to(self.workspace):
            raise GatewayError("unsafe_artifact_path", "Artifact directory escapes the configured workspace.")

    def _path(self, digest, *, create=False):
        if type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise GatewayError("invalid_request", "Artifacts are selected only by a lowercase SHA-256 digest.")
        self._check_directory(self.workspace)
        self._check_directory(self.root)
        directory = self.root / digest[:2]
        if create:
            directory.mkdir(mode=0o700, exist_ok=True)
        if not directory.exists():
            raise GatewayError("artifact_not_found", "The requested artifact is unavailable.")
        self._check_directory(directory)
        return directory / digest

    def _open_verified(self, digest):
        path = self._path(digest)
        stream = None
        try:
            info = path.lstat()
            if _unsafe_link(path) or not stat.S_ISREG(info.st_mode):
                raise GatewayError("unsafe_artifact_path", "Artifact links or reparse points are not accepted.")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            stream = os.fdopen(fd, "rb")
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > self.max_artifact_bytes:
                stream.close()
                raise GatewayError("artifact_integrity_error", "Artifact type or byte count is invalid.")
            fingerprint = self._fingerprint(info)
            actual = hashlib.sha256()
            remaining = info.st_size
            while remaining:
                chunk = stream.read(min(remaining, 128*1024))
                if not chunk:
                    raise GatewayError("artifact_integrity_error", "Artifact bytes changed during verification.")
                actual.update(chunk)
                remaining -= len(chunk)
            if stream.read(1) or actual.hexdigest() != digest or self._fingerprint(os.fstat(stream.fileno())) != fingerprint:
                raise GatewayError("artifact_integrity_error", "Artifact content does not match its SHA-256 address.")
            stream.seek(0)
            return stream, info.st_size, fingerprint
        except GatewayError:
            if stream is not None:
                stream.close()
            raise
        except FileNotFoundError as exc:
            raise GatewayError("artifact_not_found", "The requested artifact is unavailable.") from exc
        except OSError as exc:
            if stream is not None:
                stream.close()
            raise GatewayError("artifact_unavailable", "The artifact cannot be opened safely.") from exc

    @staticmethod
    def _fingerprint(info):
        # Link-count/ctime changes during atomic POSIX publication do not change
        # the already complete content. Every read still hashes the full bytes.
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)

    def put_bytes(self, data: bytes, *, media_type: str = "application/octet-stream") -> ArtifactReference:
        if type(data) is not bytes or len(data) > self.max_artifact_bytes:
            raise GatewayError("artifact_too_large", "Artifact bytes exceed the configured store budget.")
        if type(media_type) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*", media_type):
            raise GatewayError("invalid_request", "An artifact requires an explicit valid media type.")
        digest = hashlib.sha256(data).hexdigest()
        path = self._path(digest, create=True)
        if path.exists() or path.is_symlink():
            stream, size, _ = self._open_verified(digest)
            stream.close()
            if size != len(data):
                raise GatewayError("artifact_integrity_error", "An existing artifact has a different byte count.")
            return ArtifactReference(digest, len(data), media_type, "meshvenn-artifact://"+digest)
        temporary = None
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_directory(path.parent)
            try:
                # Both operations publish atomically and fail if the address
                # already exists. Never replace an accepted artifact in place.
                if os.name == "nt":
                    os.rename(temporary, path)
                else:
                    os.link(temporary, path)
            except FileExistsError:
                stream, _, _ = self._open_verified(digest)
                stream.close()
            stream, _, _ = self._open_verified(digest)
            stream.close()
            return ArtifactReference(digest, len(data), media_type, "meshvenn-artifact://"+digest)
        except GatewayError:
            raise
        except OSError as exc:
            raise GatewayError("artifact_unavailable", "The filesystem could not atomically publish the immutable artifact.") from exc
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    def read(self, sha256: str, *, offset: int = 0, limit: int = 64*1024):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= self.max_chunk_bytes:
            raise GatewayError("invalid_request", "Artifact offset/limit must be nonnegative/bounded integers.")
        stream, size, fingerprint = self._open_verified(sha256)
        with stream:
            if offset > size:
                raise GatewayError("invalid_request", "Artifact offset exceeds its verified byte count.")
            stream.seek(offset)
            before = self._fingerprint(os.fstat(stream.fileno()))
            if before != fingerprint:
                raise GatewayError("artifact_integrity_error", "Artifact changed after its SHA-256 verification.")
            chunk = stream.read(limit)
            if self._fingerprint(os.fstat(stream.fileno())) != before:
                raise GatewayError("artifact_integrity_error", "Artifact changed during its verified chunk read.")
        return dict(schema_version=1, status="completed", sha256=sha256, offset=offset, bytes=len(chunk),
                    total_bytes=size, eof=offset+len(chunk) == size,
                    next_offset=offset+len(chunk),
                    data_base64=base64.b64encode(chunk).decode("ascii"), error=None)
