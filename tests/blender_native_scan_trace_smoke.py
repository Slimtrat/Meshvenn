"""Compare the incremental native scan with the historical bulk API."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    package_root = parser.parse_args(arguments).package_root.resolve()
    sys.path.insert(0, str(package_root.parent))
    package = package_root.name

    bridge = importlib.import_module(f"{package}.core.native_bridge")
    masks = importlib.import_module(f"{package}.core.image_mask")
    trace_module = importlib.import_module(f"{package}.core.native_scan_trace")

    full = masks.BinaryMask(16, 16, bytes([1] * 256))
    empty = masks.BinaryMask(16, 16, bytes(256))
    front = bridge.NativeProjection(full, 0.0)
    side = bridge.NativeProjection(full, 90.0)
    conflicting = bridge.NativeProjection(empty, 180.0)
    core = bridge.NativeCore()

    bulk = core.build_visual_hull((front, side), resolution=16)
    traced = trace_module.scan_named_projections(
        core, (("front", front), ("side", side)), resolution=16
    )
    assert traced.volume == bulk, "Incremental and bulk visual hull results differ"
    assert len(traced.views) == 2
    assert traced.views[0].before == 16 ** 3
    assert traced.views[-1].after == traced.volume.occupied_count

    emptied = trace_module.scan_named_projections(
        core,
        (("front", front), ("contradictory", conflicting), ("side", side)),
        resolution=16,
    )
    assert emptied.volume.occupied_count == 0
    assert emptied.emptying_view == "contradictory"
    assert len(emptied.views) == 2, "Scan should stop after the emptying view"
    print("Native scan trace parity and emptying-view diagnostics OK")


if __name__ == "__main__":
    main()
