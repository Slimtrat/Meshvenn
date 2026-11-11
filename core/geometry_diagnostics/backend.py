"""Killable native execution. No DLL calls run in the Blender/UI process."""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..native_loader import EXPECTED_ABI_VERSION, find_native_library
from ..native_bridge import NativeProjection
from .models import SequentialTraceStep, VolumeArtifact


@dataclass(frozen=True)
class NativeExperiment:
    experiment_id: str
    included_view_ids: tuple[str, ...]
    volume: VolumeArtifact
    trace: tuple[SequentialTraceStep, ...]
    elapsed_seconds: float


@dataclass(frozen=True)
class NativeBatch:
    experiments: tuple[NativeExperiment, ...]
    state: str
    error: str
    library_sha256: str
    python_executable: str
    elapsed_seconds: float
    termination: str


class NativeGeometryBackend:
    """The official NativeCore bridge in a separate, disposable Python host.

    ``sys.executable`` is suitable in a normal CPython process. Blender's binary
    is deliberately rejected: a Blender host must supply a Python executable.
    The parent terminates and reaps this child on deadline/cancellation, including
    when a DLL call blocks. Completed, atomically saved sessions survive timeout.
    """

    def __init__(self, library_path: Path | None = None, *, python_executable: Path | None = None):
        self.library_path = Path(library_path) if library_path is not None else None
        self.python_executable = Path(python_executable) if python_executable is not None else Path(sys.executable)

    def run(self, projections: Sequence[tuple[str, NativeProjection]], *, resolution: int,
            input_order: Sequence[str], timeout: float, thread_count: int = 1,
            cancel: Callable[[], bool] | None = None) -> NativeBatch:
        started = time.monotonic()
        try:
            return self._run(projections, resolution=resolution, input_order=input_order,
                             timeout=timeout, thread_count=thread_count, cancel=cancel)
        except OSError as exc:
            return NativeBatch((), "worker_failure", f"Worker filesystem/launch failure: {type(exc).__name__}: {exc}",
                               "", str(self.python_executable), time.monotonic()-started, "not_started")

    def _run(self, projections: Sequence[tuple[str, NativeProjection]], *, resolution: int,
             input_order: Sequence[str], timeout: float, thread_count: int,
             cancel: Callable[[], bool] | None) -> NativeBatch:
        started = time.monotonic()
        if type(timeout) not in (int, float) or not math.isfinite(timeout):
            raise ValueError("Native deadline must be a finite number of seconds.")
        if timeout > 120:
            raise ValueError("Native diagnostic deadline must not exceed 120 seconds.")
        library_hash = ""
        python = str(self.python_executable.resolve())

        def result(state, error="", experiments=(), termination="not_started"):
            return NativeBatch(tuple(experiments), state, error, library_hash, python,
                               time.monotonic() - started, termination)

        if cancel is not None and cancel():
            return result("cancelled")
        if timeout <= 0:
            return result("time_budget")
        if not re.fullmatch(r"python(?:w|\d+(?:\.\d+)?)?(?:\.exe)?", self.python_executable.name, re.I):
            return result("host_unavailable", "Supply a CPython executable; Blender is not a Python command-line host.")
        if not self.python_executable.is_file():
            return result("host_unavailable", "Configured Python executable is unavailable.")
        try:
            library = (self.library_path or find_native_library()).resolve()
            if library.stat().st_size > 128 * 1024 * 1024:
                return result("native_failure", "Native library exceeds the 128 MiB binary budget.")
            library_hash = hashlib.sha256(library.read_bytes()).hexdigest()
        except (OSError, RuntimeError) as exc:
            return result("native_unavailable", str(exc))
        ordered = tuple(sorted(projections, key=lambda p: p[0]))
        ids = tuple(name for name, _ in ordered)
        if (not 1 <= len(ids) <= 10 or len(set(ids)) != len(ids) or
                len(input_order) != len(ids) or len(set(input_order)) != len(ids) or set(input_order) != set(ids)):
            raise ValueError("Native diagnostics require 1–10 unique views and their exact input order.")
        if type(resolution) is not int or not 8 <= resolution <= 64:
            raise ValueError("Native diagnostic resolution must be in [8,64].")
        if type(thread_count) is not int or not 1 <= thread_count <= 8:
            raise ValueError("Native diagnostics require 1–8 threads.")
        request_views = []
        for name, projection in ordered:
            mask = projection.mask
            if (type(mask.width) is not int or type(mask.height) is not int or
                    mask.width * mask.height > 1_048_576 or any(value > 1 for value in mask.values)):
                raise ValueError("Native diagnostic masks exceed their binary/pixel contract.")
            request_views.append(dict(view_id=name, width=mask.width, height=mask.height,
                                      values_hex=mask.values.hex(), azimuth=projection.azimuth_degrees,
                                      elevation=projection.elevation_degrees, flip_x=projection.flip_x))
        specifications = [("full", ids)]
        if len(ids) > 1:
            specifications.extend((f"without-{name}", tuple(i for i in ids if i != name)) for name in ids)
        if tuple(input_order) != ids:
            specifications.append(("source-order", tuple(input_order)))
        request = dict(schema_version=1, library_path=str(library), library_sha256=library_hash,
                       abi=EXPECTED_ABI_VERSION, resolution=resolution, thread_count=thread_count,
                       views=request_views, experiments=specifications)
        package_root = Path(__file__).resolve().parents[2]
        deadline = started + timeout
        process = None
        state, error, termination = "complete", "", "exited"
        with tempfile.TemporaryDirectory(prefix="meshvenn-geometry-") as directory:
            directory = Path(directory)
            request_path = directory / "request.json"
            request_path.write_text(json.dumps(request, allow_nan=False, separators=(",", ":")), encoding="utf-8")
            bootstrap = "import sys;sys.path.insert(0,sys.argv[1]);from core.geometry_diagnostics.worker import main;main(sys.argv[2:])"
            command = [python, "-I", "-c", bootstrap, str(package_root), str(request_path), str(directory)]
            try:
                with (directory / "worker.log").open("wb") as log:
                    if time.monotonic() >= deadline:
                        return result("time_budget")
                    process = subprocess.Popen(command, cwd=package_root, stdin=subprocess.DEVNULL,
                                               stdout=log, stderr=log,
                                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    while process.poll() is None:
                        if cancel is not None and cancel():
                            state, termination = "cancelled", "terminated_cancelled"
                            break
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            state, termination = "time_budget", "terminated_deadline"
                            break
                        try:
                            process.wait(timeout=min(0.05, remaining))
                        except subprocess.TimeoutExpired:
                            pass
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=2)
                            termination += "_killed"
                completed = []
                for index, (experiment_id, included) in enumerate(specifications):
                    path = directory / f"experiment-{index:02d}.json"
                    if not path.is_file():
                        break
                    if path.stat().st_size > 2_000_000:
                        raise ValueError("Native worker artifact exceeds its bounded protocol.")
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data["experiment_id"] != experiment_id or tuple(data["included_view_ids"]) != included:
                        raise ValueError("Native worker returned a different experiment.")
                    volume = VolumeArtifact.from_dict(data["volume"])
                    if volume.width != resolution:
                        raise ValueError("Native worker returned a different resolution.")
                    trace = tuple(SequentialTraceStep.from_dict(step) for step in data["trace"])
                    if tuple(step.view_id for step in trace) != included:
                        raise ValueError("Native worker returned an incomplete sequential trace.")
                    completed.append(NativeExperiment(experiment_id, included, volume, trace, float(data["elapsed_seconds"])))
                status_path = directory / "status.json"
                if state == "complete":
                    if status_path.is_file():
                        status = json.loads(status_path.read_text(encoding="utf-8"))
                        state, error = status["state"], status.get("error", "")
                    if process.returncode != 0 and state == "complete":
                        state, error = "worker_failure", f"Native worker exited with code {process.returncode}."
                    if state == "complete" and len(completed) != len(specifications):
                        state, error = "worker_failure", "Native worker exited without all requested experiments."
                return result(state, error, completed, termination)
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                return result("worker_failure", f"{type(exc).__name__}: {exc}", termination=termination)
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)


def host_platform():
    return f"{platform.system()}-{platform.machine()}-{platform.python_implementation()}-{platform.python_version()}"
