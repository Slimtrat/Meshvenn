from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScanProfile:
    name: str
    views: tuple[str, ...]
    description: str


PROFILES: tuple[ScanProfile, ...] = (
    ScanProfile(
        name="L2",
        views=("000", "090"),
        description="Face + profil droit",
    ),
    ScanProfile(
        name="L4",
        views=("000", "090", "180", "270"),
        description="Face + profils + dos",
    ),
    ScanProfile(
        name="L8",
        views=("000", "045", "090", "135", "180", "225", "270", "315"),
        description="Turntable horizontal complet",
    ),
    ScanProfile(
        name="L10",
        views=(
            "000", "045", "090", "135", "180",
            "225", "270", "315", "TOP", "BOT",
        ),
        description="Turntable complet + dessus + dessous",
    ),
)


def available_profiles(available_views: set[str]) -> list[ScanProfile]:
    return [
        profile
        for profile in PROFILES
        if set(profile.views).issubset(available_views)
    ]


def get_profile(name: str) -> ScanProfile:
    normalized = name.upper()

    for profile in PROFILES:
        if profile.name == normalized:
            return profile

    raise KeyError(f"Unknown scan profile: {name}")
