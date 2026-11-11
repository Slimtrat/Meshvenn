"""Internal isolated native worker; no network, Blender, or alternate engine."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

from ..image_mask import BinaryMask
from ..native_bridge import NativeCore, NativeCoreError, NativeProjection
from ..native_loader import NativeAbiMismatchError, NativeLibraryLoadError
from .models import SequentialTraceStep, VolumeArtifact


def _write(path, value):
    temporary = path.with_suffix(".pending")
    temporary.write_text(json.dumps(value, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    request_path, directory = map(Path, arguments)
    try:
        if request_path.stat().st_size > 24_000_000:
            raise ValueError("Native worker request exceeds 24 MiB.")
        request = json.loads(request_path.read_text(encoding="utf-8"))
        resolution = request["resolution"]
        if request["schema_version"] != 1 or type(resolution) is not int or not 8 <= resolution <= 64:
            raise ValueError("Unsupported native diagnostic request.")
        if not 1 <= len(request["views"]) <= 10 or not 1 <= len(request["experiments"]) <= 12:
            raise ValueError("Native request exceeds view/session budget.")
        library = Path(request["library_path"])
        if hashlib.sha256(library.read_bytes()).hexdigest() != request["library_sha256"]:
            raise ValueError("Native library changed before isolated execution.")
        projections = {}
        for entry in request["views"]:
            mask = BinaryMask(entry["width"], entry["height"], bytes.fromhex(entry["values_hex"]))
            if mask.width * mask.height > 1_048_576 or any(v > 1 for v in mask.values):
                raise ValueError("Invalid native source mask.")
            projections[entry["view_id"]] = NativeProjection(mask, entry["azimuth"], entry["elevation"], entry["flip_x"])
        core = NativeCore(library_path=library)
        for index, (experiment_id, included) in enumerate(request["experiments"]):
            started = time.monotonic()
            before, trace = resolution ** 3, []
            with core.create_session(resolution=resolution, symmetry_x=False,
                                     thread_count=request["thread_count"]) as session:
                for order_index, view_id in enumerate(included):
                    after = session.apply_projection(projections[view_id])
                    trace.append(SequentialTraceStep(view_id, order_index, before, after))
                    before = after
                volume = VolumeArtifact.from_native(session.snapshot())
                if before != volume.occupied_count:
                    raise RuntimeError("Native session occupancy disagrees with snapshot.")
            _write(directory / f"experiment-{index:02d}.json",
                   dict(experiment_id=experiment_id, included_view_ids=included, volume=volume.to_dict(),
                        trace=[step.to_dict() for step in trace], elapsed_seconds=time.monotonic() - started))
        _write(directory / "status.json", dict(state="complete"))
    except (NativeCoreError, NativeLibraryLoadError, NativeAbiMismatchError) as exc:
        _write(directory / "status.json", dict(state="native_failure", error=f"{type(exc).__name__}: {exc}"))
    except Exception as exc:
        _write(directory / "status.json", dict(state="worker_failure", error=f"{type(exc).__name__}: {exc}"))


if __name__ == "__main__":
    main()
