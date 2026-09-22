from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from core import ViewScanDiagnostic
from core.native_scan import INCREMENTAL_VIEW_ORDER, NativeScanner


class FakeSession:
    def __init__(self, survivors: dict[str, int]) -> None:
        self.survivors = survivors
        self.applied: list[str] = []
        self.current_count = 0

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def apply_projection(self, view: str) -> int:
        self.applied.append(view)
        self.current_count = self.survivors[view]
        return self.current_count

    def snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(occupied_count=self.current_count)


class FakeCore:
    def __init__(self, survivors: dict[str, int]) -> None:
        self.session = FakeSession(survivors)
        self.created = False

    def create_session(self, **_options: object) -> FakeSession:
        self.created = True
        return self.session


class NativeScanDiagnosticTests(unittest.TestCase):
    def test_value_object_reports_stable_json_fields(self) -> None:
        diagnostic = ViewScanDiagnostic("090", 1, 100, 10)
        self.assertEqual(diagnostic.removed_count, 90)
        self.assertEqual(diagnostic.retained_fraction, 0.1)
        self.assertEqual(diagnostic.status, "sharp-drop")
        self.assertEqual(
            diagnostic.as_dict(),
            {
                "view": "090",
                "order_index": 1,
                "before": 100,
                "after": 10,
                "removed_count": 90,
                "retained_fraction": 0.1,
                "status": "sharp-drop",
            },
        )
        self.assertEqual(ViewScanDiagnostic("000", 0, 100, 1).status, "ok")
        self.assertEqual(ViewScanDiagnostic("090", 1, 10, 0).status, "empty")
        self.assertEqual(ViewScanDiagnostic("000", 0, 0, 0).retained_fraction, 0.0)
        with self.assertRaises(FrozenInstanceError):
            diagnostic.after = 9

    def test_invalid_counts_are_rejected(self) -> None:
        for values in (("", 0, 1, 1), ("000", -1, 1, 1),
                       ("000", 0, -1, 0), ("000", 0, 1, -1),
                       ("000", 0, 1, 2)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ViewScanDiagnostic(*values)

    def test_l2_records_canonical_order_and_monotone_counts(self) -> None:
        core = FakeCore({"000": 100, "090": 90})
        result = NativeScanner(core=core).scan_levels(
            {"090": "090", "000": "000"},
            resolution=5,
            levels=["L2"],
            build_meshes=False,
        )
        self.assertEqual(core.session.applied, ["000", "090"])
        self.assertEqual(result.generated_levels, ("L2",))
        self.assertEqual(result.snapshots["L2"].applied_views, ("000", "090"))
        self.assertEqual(
            result.view_diagnostics,
            (
                ViewScanDiagnostic("000", 0, 125, 100),
                ViewScanDiagnostic("090", 1, 100, 90),
            ),
        )

    def test_l10_reports_each_view_and_sharp_drop(self) -> None:
        counts = (100, 95, 9, 8, 7, 6, 5, 4, 3, 2)
        survivors = dict(zip(INCREMENTAL_VIEW_ORDER, counts))
        core = FakeCore(survivors)
        result = NativeScanner(core=core).scan_levels(
            {view: view for view in reversed(INCREMENTAL_VIEW_ORDER)},
            resolution=5,
            levels=["L10"],
            build_meshes=False,
        )
        self.assertEqual(result.generated_levels, ("L10",))
        self.assertEqual(len(result.view_diagnostics), 10)
        self.assertEqual(
            tuple(item.view for item in result.view_diagnostics),
            INCREMENTAL_VIEW_ORDER,
        )
        self.assertEqual(result.view_diagnostics[2].status, "sharp-drop")
        self.assertEqual(result.view_diagnostics[-1].after, 2)
        for previous, current in zip(
            result.view_diagnostics, result.view_diagnostics[1:]
        ):
            self.assertEqual(previous.after, current.before)

    def test_contradictory_view_is_recorded_before_early_stop(self) -> None:
        survivors = {view: 100 - index * 10 for index, view in enumerate(INCREMENTAL_VIEW_ORDER)}
        survivors["045"] = 0
        core = FakeCore(survivors)
        result = NativeScanner(core=core).scan_levels(
            {view: view for view in INCREMENTAL_VIEW_ORDER},
            resolution=5,
            build_meshes=False,
        )
        self.assertEqual(result.generated_levels, ("L2", "L4"))
        self.assertEqual(core.session.applied[-1], "045")
        self.assertEqual(result.view_diagnostics[-1].view, "045")
        self.assertEqual(result.view_diagnostics[-1].status, "empty")
        self.assertEqual(len(result.view_diagnostics), 5)

    def test_missing_runnable_levels_have_no_diagnostics_or_session(self) -> None:
        core = FakeCore({"000": 100})
        result = NativeScanner(core=core).scan_levels(
            {"000": "000"}, resolution=5, levels=["L2", "L10"]
        )
        self.assertFalse(core.created)
        self.assertEqual(result.requested_levels, ("L2", "L10"))
        self.assertEqual(result.available_views, ("000",))
        self.assertEqual(result.generated_levels, ())
        self.assertEqual(result.view_diagnostics, ())


if __name__ == "__main__":
    unittest.main()
