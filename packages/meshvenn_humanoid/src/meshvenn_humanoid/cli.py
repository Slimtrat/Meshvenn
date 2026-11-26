"""Host CLI. Paths are local host configuration; no remote code/provider input."""

import argparse, os, subprocess
from pathlib import Path
from .models import Budget


def main():
    p = argparse.ArgumentParser(
        description="Automatically inspect and regenerate a native humanoid rig"
    )
    p.add_argument("--blender", type=Path, required=True)
    p.add_argument("--engine-root", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--object")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--max-attempts", type=int, default=4)
    p.add_argument("--max-seconds", type=float, default=180.0)
    a = p.parse_args()
    Budget(a.max_attempts, a.max_seconds)
    worker = Path(__file__).with_name("blender") / "worker.py"
    command = [
        str(a.blender.resolve()),
        "--background",
        "--factory-startup",
        "--disable-autoexec",
        "--python-exit-code",
        "1",
        "--python",
        str(worker),
        "--",
        "--engine-root",
        str(a.engine_root.resolve()),
        "--source",
        str(a.source.resolve()),
        "--output",
        str(a.output.resolve()),
        "--max-attempts",
        str(a.max_attempts),
        "--max-seconds",
        str(a.max_seconds),
    ]
    if a.object:
        command += ["--object", a.object]
    if a.resume:
        command += ["--resume"]
        marker = a.output / "cancel.request"
        if marker.is_file():
            marker.unlink()
    process = subprocess.Popen(
        command, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    )
    try:
        return process.wait(timeout=a.max_seconds + 30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        return 124
    except KeyboardInterrupt:
        a.output.mkdir(parents=True, exist_ok=True)
        (a.output / "cancel.request").write_text("cancel\n")
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 130
