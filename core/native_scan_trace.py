"""Per-view trace for the native visual-hull engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .native_bridge import NativeCore, NativeProjection, NativeVolume
from .native_scan_diagnostics import ViewScanDiagnostic


@dataclass(frozen=True)
class VisualHullTrace:
    volume: NativeVolume
    views: tuple[ViewScanDiagnostic, ...]

    @property
    def emptying_view(self) -> str | None:
        return next((view.view for view in self.views if view.status == "empty"), None)

    @property
    def sharp_drop_views(self) -> tuple[str, ...]:
        return tuple(view.view for view in self.views if view.status == "sharp-drop")


def scan_named_projections(
    core: NativeCore,
    projections: Iterable[tuple[str, NativeProjection]],
    *,
    resolution: int,
    symmetry_x: bool = False,
    thread_count: int = 0,
) -> VisualHullTrace:
    """Scan in source order and retain the voxel count after each projection."""

    ordered = tuple(projections)
    if len(ordered) < 2:
        raise ValueError("At least two projections are required.")
    if resolution <= 0:
        raise ValueError("Resolution must be greater than zero.")

    before = resolution ** 3
    views: list[ViewScanDiagnostic] = []
    with core.create_session(
        resolution=resolution,
        symmetry_x=symmetry_x,
        thread_count=thread_count,
    ) as session:
        for index, (name, projection) in enumerate(ordered):
            after = session.apply_projection(projection)
            diagnostic = ViewScanDiagnostic(
                view=name,
                order_index=index,
                before=before,
                after=after,
            )
            views.append(diagnostic)
            before = after
            if after == 0:
                break
        volume = session.snapshot()

    if volume.occupied_count != before:
        raise RuntimeError("Native scan snapshot disagrees with the last view count.")
    return VisualHullTrace(volume=volume, views=tuple(views))
