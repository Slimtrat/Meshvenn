"""Trusted runtime configuration and killable native mesh execution adapter."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .core.native_loader import find_native_library
from .errors import EngineError

MAX_MESH_JSON_BYTES = 33_554_432
MAX_MESH_VERTICES = 262_144
MAX_MESH_INDICES = 1_048_576
MAX_EXPOSED_FACES = 65_536


class NativeRuntime:
    def __init__(self, native_library=None, python_executable=None):
        self.library = Path(native_library).resolve() if native_library is not None else None
        self.python = Path(python_executable or sys.executable).resolve()

    def paths(self):
        if not re.fullmatch(r"python(?:w|\d+(?:\.\d+)?)?(?:\.exe)?", self.python.name, re.I) or not self.python.is_file():
            raise EngineError("host_unavailable", "Configure a CPython executable in the trusted engine constructor.")
        try:
            library = self.library or find_native_library().resolve()
            if not library.is_file() or library.stat().st_size > 134_217_728:
                raise OSError("Missing or oversized native library")
        except (OSError, RuntimeError) as exc:
            raise EngineError("native_unavailable", "Configure an existing native ABI 1 library in the trusted engine constructor.") from exc
        return library, self.python

    def availability(self):
        try:
            self.paths()
            return True, "Native runtime configured; ABI validation occurs inside the isolated worker."
        except EngineError as exc:
            return False, exc.message

    def mesh(self, arguments, *, cancel=None):
        started = time.monotonic()
        deadline = started + arguments["max_seconds"]
        library, python = self.paths()
        request = dict(arguments, library_path=str(library),
                       library_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
        package_parent = Path(__file__).resolve().parent.parent
        bootstrap = "import sys;sys.path.insert(0,sys.argv[1]);from meshvenn_engine._mesh_worker import main;main(sys.argv[2:])"
        process = None
        try:
            with tempfile.TemporaryDirectory(prefix="meshvenn-mesh-") as directory:
                directory = Path(directory)
                source, target = directory / "request.json", directory / "result.json"
                source.write_text(json.dumps(request, allow_nan=False, separators=(",", ":")), encoding="utf-8")
                command = [str(python), "-I", "-c", bootstrap, str(package_parent), str(source), str(target)]
                with (directory / "worker.log").open("wb") as log:
                    if cancel is not None and cancel():
                        raise EngineError("cancelled", "Native mesh execution was cancelled before launch.")
                    if time.monotonic() >= deadline:
                        raise EngineError("timeout", "Native mesh deadline expired before launch.")
                    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        cwd=directory, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    try:
                        while process.poll() is None:
                            if cancel is not None and cancel():
                                raise EngineError("cancelled", "Native mesh execution was cancelled.")
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                raise EngineError("timeout", "Native mesh exceeded its shared process deadline.")
                            try:
                                process.wait(timeout=min(.05, remaining))
                            except subprocess.TimeoutExpired:
                                pass
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=.5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=2)
                if process.returncode != 0 or not target.is_file():
                    raise EngineError("native_failure", "The isolated native mesh worker did not return a complete result.")
                if target.stat().st_size > MAX_MESH_JSON_BYTES:
                    raise EngineError("resource_limit", "Native mesh response exceeds its 32 MiB output budget.")
                response = json.loads(target.read_text(encoding="utf-8"))
                if response.get("ok") is not True:
                    error = response.get("error", {})
                    raise EngineError(error.get("code", "native_failure"), error.get("message", "Native mesh worker failed."))
                result = response["result"]
                if (result["provenance"]["native_library_sha256"] != request["library_sha256"]
                        or result["provenance"]["source_volume_sha256"] != arguments["volume"]["sha256"]):
                    raise EngineError("native_failure", "Native mesh response provenance differs from its trusted request.")
                return result
        except EngineError:
            raise
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            raise EngineError("native_failure", f"Native mesh host failed: {type(exc).__name__}.") from exc
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=2)
