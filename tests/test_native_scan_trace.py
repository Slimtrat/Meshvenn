from __future__ import annotations

import unittest

from core.native_bridge import NativeVolume
from core.native_scan_trace import scan_named_projections


class FakeSession:
    def __init__(self, counts: tuple[int, ...], resolution: int) -> None:
        self.counts = iter(counts)
        self.resolution = resolution
        self.last_count = resolution ** 3
        self.applied: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def apply_projection(self, projection: object) -> int:
        self.applied.append(projection)
        self.last_count = next(self.counts)
        return self.last_count

    def snapshot(self) -> NativeVolume:
        total = self.resolution ** 3
        return NativeVolume(
            self.resolution,
            self.resolution,
            self.resolution,
            bytes([1] * self.last_count + [0] * (total - self.last_count)),
            self.last_count,
            None,
        )


class FakeCore:
    def __init__(self, counts: tuple[int, ...]) -> None:
        self.counts = counts
        self.session: FakeSession | None = None
        self.options: dict | None = None

    def create_session(self, **options) -> FakeSession:
        self.options = options
        self.session = FakeSession(self.counts, options["resolution"])
        return self.session


class NativeScanTraceTests(unittest.TestCase):
    def test_records_source_order_and_counts(self) -> None:
        core = FakeCore((32, 16))
        trace = scan_named_projections(
            core, (("front", object()), ("side", object())),
            resolution=4, symmetry_x=True, thread_count=2,
        )
        self.assertEqual([view.view for view in trace.views], ["front", "side"])
        self.assertEqual([(view.before, view.after) for view in trace.views], [(64, 32), (32, 16)])
        self.assertEqual(trace.volume.occupied_count, 16)
        self.assertEqual(core.options, {"resolution": 4, "symmetry_x": True, "thread_count": 2})
        self.assertEqual(len(core.session.applied), 2)

    def test_emptying_view_stops_before_later_projections(self) -> None:
        core = FakeCore((32, 0))
        trace = scan_named_projections(
            core,
            (("front", object()), ("bad", object()), ("unused", object())),
            resolution=4,
        )
        self.assertEqual(trace.emptying_view, "bad")
        self.assertEqual(len(trace.views), 2)
        self.assertEqual(len(core.session.applied), 2)
        self.assertEqual(trace.volume.occupied_count, 0)

    def test_sharp_drop_is_warning_not_rejection(self) -> None:
        trace = scan_named_projections(
            FakeCore((40, 3)), (("front", object()), ("side", object())), resolution=4
        )
        self.assertEqual(trace.sharp_drop_views, ("side",))
        self.assertEqual(trace.volume.occupied_count, 3)


if __name__ == "__main__":
    unittest.main()
