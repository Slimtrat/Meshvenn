from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .native_bridge import (
    NativeCore,
    NativeMesh,
    NativeProjection,
    NativeVolume,
)


# ---------------------------------------------------------
# Canonical incremental scan order
# ---------------------------------------------------------

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


@dataclass(frozen=True)
class ScanLevel:
    name: str
    views: tuple[str, ...]
    snapshot_after: str


SCAN_LEVELS: tuple[ScanLevel, ...] = (
    ScanLevel(
        name="L2",
        views=(
            "000",
            "090",
        ),
        snapshot_after="090",
    ),
    ScanLevel(
        name="L4",
        views=(
            "000",
            "090",
            "180",
            "270",
        ),
        snapshot_after="270",
    ),
    ScanLevel(
        name="L8",
        views=(
            "000",
            "090",
            "180",
            "270",
            "045",
            "135",
            "225",
            "315",
        ),
        snapshot_after="315",
    ),
    ScanLevel(
        name="L10",
        views=(
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
        ),
        snapshot_after="BOT",
    ),
)


LEVEL_BY_NAME: dict[str, ScanLevel] = {
    level.name: level
    for level in SCAN_LEVELS
}


LEVEL_ORDER: dict[str, int] = {
    level.name: index
    for index, level
    in enumerate(SCAN_LEVELS)
}


SNAPSHOT_LEVEL_BY_VIEW: dict[str, str] = {
    level.snapshot_after: level.name
    for level in SCAN_LEVELS
}


VALID_LEVEL_NAMES = frozenset(
    LEVEL_BY_NAME
)


# ---------------------------------------------------------
# Results
# ---------------------------------------------------------

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

    @property
    def generated_levels(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            level.name
            for level in SCAN_LEVELS
            if level.name in self.snapshots
        )


# ---------------------------------------------------------
# Scanner
# ---------------------------------------------------------

class NativeScanner:
    def __init__(
        self,
        *,
        core: NativeCore | None = None,
    ) -> None:
        self.core = (
            core
            if core is not None
            else NativeCore()
        )

    def scan_levels(
        self,
        projections: dict[
            str,
            NativeProjection,
        ],
        *,
        resolution: int,
        levels: Iterable[str] | None = None,
        symmetry_x: bool = False,
        thread_count: int = 0,
        build_meshes: bool = True,
        voxel_size: float = 1.0,
        center_xy: bool = True,
        mesh_mode: str = "blocks",
    ) -> NativeScanResult:
        if resolution <= 0:
            raise ValueError(
                "Resolution must be greater than zero."
            )

        normalized_projections = (
            self._normalize_projections(
                projections
            )
        )

        requested_levels = (
            self._normalize_levels(
                levels
            )
        )

        available_views = tuple(
            view
            for view in INCREMENTAL_VIEW_ORDER
            if view in normalized_projections
        )

        runnable_levels = (
            self._resolve_runnable_levels(
                requested_levels,
                normalized_projections,
            )
        )

        if not runnable_levels:
            return NativeScanResult(
                snapshots={},
                requested_levels=(
                    requested_levels
                ),
                available_views=(
                    available_views
                ),
            )

        highest_level_name = max(
            runnable_levels,
            key=LEVEL_ORDER.__getitem__,
        )

        highest_level = (
            LEVEL_BY_NAME[
                highest_level_name
            ]
        )

        required_views = frozenset(
            highest_level.views
        )

        snapshot_levels = frozenset(
            runnable_levels
        )

        snapshots: dict[
            str,
            ScanSnapshot,
        ] = {}

        applied_views: list[str] = []

        with self.core.create_session(
            resolution=resolution,
            symmetry_x=symmetry_x,
            thread_count=thread_count,
        ) as session:
            for view_name in (
                INCREMENTAL_VIEW_ORDER
            ):
                if (
                    view_name
                    not in required_views
                ):
                    continue

                projection = (
                    normalized_projections[
                        view_name
                    ]
                )

                surviving_voxels = (
                    session.apply_projection(
                        projection
                    )
                )

                applied_views.append(
                    view_name
                )

                level_name = (
                    SNAPSHOT_LEVEL_BY_VIEW.get(
                        view_name
                    )
                )

                if (
                    level_name is None
                    or level_name
                    not in snapshot_levels
                ):
                    if surviving_voxels == 0:
                        break

                    continue

                volume = (
                    session.snapshot()
                )

                mesh = None

                if (
                    build_meshes
                    and volume.occupied_count > 0
                ):
                    mesh = (
                        self.core
                        .build_surface_mesh(
                            volume,
                            voxel_size=(
                                voxel_size
                            ),
                            center_xy=(
                                center_xy
                            ),
                            mesh_mode=(
                                mesh_mode
                            ),
                        )
                    )

                snapshots[
                    level_name
                ] = ScanSnapshot(
                    level=level_name,
                    volume=volume,
                    mesh=mesh,
                    applied_views=tuple(
                        applied_views
                    ),
                )

                if surviving_voxels == 0:
                    break

        return NativeScanResult(
            snapshots=snapshots,
            requested_levels=(
                requested_levels
            ),
            available_views=(
                available_views
            ),
        )

    @staticmethod
    def _normalize_projections(
        projections: dict[
            str,
            NativeProjection,
        ],
    ) -> dict[
        str,
        NativeProjection,
    ]:
        normalized: dict[
            str,
            NativeProjection,
        ] = {}

        for raw_name, projection in (
            projections.items()
        ):
            name = (
                str(raw_name)
                .strip()
                .upper()
            )

            if (
                name
                not in INCREMENTAL_VIEW_ORDER
            ):
                continue

            normalized[
                name
            ] = projection

        return normalized

    @staticmethod
    def _normalize_levels(
        levels: Iterable[str] | None,
    ) -> tuple[str, ...]:
        if levels is None:
            return tuple(
                level.name
                for level in SCAN_LEVELS
            )

        requested = {
            str(level)
            .strip()
            .upper()
            for level in levels
        }

        unknown = (
            requested
            - VALID_LEVEL_NAMES
        )

        if unknown:
            names = ", ".join(
                sorted(
                    unknown
                )
            )

            raise ValueError(
                f"Unknown scan level(s): {names}"
            )

        # Always restore canonical order.
        return tuple(
            level.name
            for level in SCAN_LEVELS
            if level.name in requested
        )

    @staticmethod
    def _resolve_runnable_levels(
        requested_levels: tuple[
            str,
            ...,
        ],
        projections: dict[
            str,
            NativeProjection,
        ],
    ) -> tuple[str, ...]:
        available = frozenset(
            projections
        )

        return tuple(
            level_name
            for level_name
            in requested_levels
            if frozenset(
                LEVEL_BY_NAME[
                    level_name
                ].views
            ).issubset(
                available
            )
        )