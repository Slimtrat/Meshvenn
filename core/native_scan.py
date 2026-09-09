from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .native_bridge import (
    NativeCore,
    NativeMesh,
    NativeProjection,
    NativeVolume,
)


@dataclass(frozen=True)
class ScanLevel:
    name: str
    views: tuple[str, ...]


SCAN_LEVELS: tuple[ScanLevel, ...] = (
    ScanLevel(
        name="L2",
        views=(
            "000",
            "090",
        ),
    ),
    ScanLevel(
        name="L4",
        views=(
            "000",
            "090",
            "180",
            "270",
        ),
    ),
    ScanLevel(
        name="L8",
        views=(
            "000",
            "045",
            "090",
            "135",
            "180",
            "225",
            "270",
            "315",
        ),
    ),
    ScanLevel(
        name="L10",
        views=(
            "000",
            "045",
            "090",
            "135",
            "180",
            "225",
            "270",
            "315",
            "TOP",
            "BOT",
        ),
    ),
)


INCREMENTAL_VIEW_ORDER: tuple[str, ...] = (
    "000",
    "090",
    "180",
    "270",
    "045",
    "135",
    "225",
    "315",
    "TOP",
    "BOT",
)


SNAPSHOT_AFTER_VIEW: dict[str, str] = {
    "090": "L2",
    "270": "L4",
    "315": "L8",
    "BOT": "L10",
}


@dataclass(frozen=True)
class ScanSnapshot:
    level: str
    volume: NativeVolume
    mesh: NativeMesh | None
    applied_views: tuple[str, ...]


@dataclass(frozen=True)
class NativeScanResult:
    snapshots: dict[str, ScanSnapshot]
    requested_levels: tuple[str, ...]
    available_views: tuple[str, ...]


class NativeScanner:
    def __init__(
        self,
        *,
        core: NativeCore | None = None,
    ) -> None:
        self.core = core or NativeCore()

    def scan_levels(
        self,
        projections: dict[str, NativeProjection],
        *,
        resolution: int,
        levels: Iterable[str] | None = None,
        symmetry_x: bool = False,
        thread_count: int = 0,
        build_meshes: bool = True,
        voxel_size: float = 1.0,
        center_xy: bool = True,
    ) -> NativeScanResult:
        requested_levels = self._normalize_levels(
            levels
        )

        runnable_levels = self._resolve_runnable_levels(
            requested_levels,
            projections,
        )

        if not runnable_levels:
            return NativeScanResult(
                snapshots={},
                requested_levels=requested_levels,
                available_views=tuple(
                    sorted(
                        projections.keys()
                    )
                ),
            )

        max_level = self._highest_level(
            runnable_levels
        )

        required_views = set(
            self._level_by_name(
                max_level
            ).views
        )

        snapshots: dict[
            str,
            ScanSnapshot
        ] = {}

        applied_views: list[str] = []

        with self.core.create_session(
            resolution=resolution,
            symmetry_x=symmetry_x,
            thread_count=thread_count,
        ) as session:
            for view_name in INCREMENTAL_VIEW_ORDER:
                if view_name not in required_views:
                    continue

                projection = projections.get(
                    view_name
                )

                if projection is None:
                    continue

                session.apply_projection(
                    projection
                )

                applied_views.append(
                    view_name
                )

                level_name = SNAPSHOT_AFTER_VIEW.get(
                    view_name
                )

                if (
                    level_name is None
                    or level_name not in runnable_levels
                ):
                    continue

                volume = session.snapshot()

                mesh = None

                if build_meshes:
                    mesh = self.core.build_surface_mesh(
                        volume,
                        voxel_size=voxel_size,
                        center_xy=center_xy,
                    )

                snapshots[level_name] = (
                    ScanSnapshot(
                        level=level_name,
                        volume=volume,
                        mesh=mesh,
                        applied_views=tuple(
                            applied_views
                        ),
                    )
                )

        return NativeScanResult(
            snapshots=snapshots,
            requested_levels=requested_levels,
            available_views=tuple(
                sorted(
                    projections.keys()
                )
            ),
        )

    def _normalize_levels(
        self,
        levels: Iterable[str] | None,
    ) -> tuple[str, ...]:
        if levels is None:
            return tuple(
                level.name
                for level in SCAN_LEVELS
            )

        normalized: list[str] = []

        for level in levels:
            name = level.upper()

            if name not in {
                item.name
                for item in SCAN_LEVELS
            }:
                raise ValueError(
                    f"Unknown scan level: {level}"
                )

            if name not in normalized:
                normalized.append(
                    name
                )

        return tuple(
            normalized
        )

    def _resolve_runnable_levels(
        self,
        requested_levels: tuple[str, ...],
        projections: dict[str, NativeProjection],
    ) -> tuple[str, ...]:
        available = set(
            projections.keys()
        )

        runnable: list[str] = []

        for level_name in requested_levels:
            level = self._level_by_name(
                level_name
            )

            if set(level.views).issubset(
                available
            ):
                runnable.append(
                    level_name
                )

        return tuple(
            runnable
        )

    def _highest_level(
        self,
        levels: tuple[str, ...],
    ) -> str:
        order = {
            level.name: index
            for index, level
            in enumerate(
                SCAN_LEVELS
            )
        }

        return max(
            levels,
            key=lambda name: order[name],
        )

    def _level_by_name(
        self,
        name: str,
    ) -> ScanLevel:
        for level in SCAN_LEVELS:
            if level.name == name:
                return level

        raise KeyError(
            name
        )