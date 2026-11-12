"""Versioned bounds and declared photometry for appearance measurements."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from ..diagnostic_contracts import ArtifactReference, DiagnosticPolicy
from ..diagnostic_contracts.codec import JsonContract, fingerprint, validate_model


@dataclass(frozen=True)
class AppearanceViewSettings(JsonContract):
    color_space: str = "unknown"
    photometry: str = "unknown"
    linear_gain: float = 1.0
    verified: bool = False
    evidence: ArtifactReference | None = None

    def __post_init__(self):
        validate_model(self)
        if self.color_space not in ("sRGB", "scene-linear", "unknown"):
            raise ValueError("Appearance color space must be sRGB, scene-linear or unknown.")
        if self.photometry not in ("albedo", "calibrated", "lit", "unknown"):
            raise ValueError("Unsupported declared photometry.")
        if not .25 <= self.linear_gain <= 4:
            raise ValueError("Declared neutral linear gain must be in [.25,4].")
        if self.photometry == "albedo" and self.linear_gain != 1:
            raise ValueError("Albedo has unit gain; declare calibrated photometry for exposure correction.")
        if self.verified and self.evidence is None:
            raise ValueError("Verified photometry requires hashed producer evidence.")

    @property
    def calibrated(self):
        return (self.verified and self.evidence is not None and self.color_space != "unknown"
                and self.photometry in ("albedo", "calibrated"))

    @property
    def dependency_fingerprint(self):
        data = self.to_dict()
        if data["evidence"] is not None:
            data["evidence"].pop("uri", None)
        return fingerprint(data)


@dataclass(frozen=True)
class AppearancePolicy:
    sampling_size: int = 64
    max_seconds: float = 30.0
    max_views: int = 20
    max_observations: int = 8
    max_references: int = 8
    max_total_pixels: int = 4_194_304
    max_samples: int = 65_536
    max_work: int = 8_000_000
    max_regions: int = 128
    min_region_samples: int = 8
    min_region_extent: int = 2
    min_changed_pixels: int = 4
    min_coverage: float = .9
    color_tolerance: float = .06
    max_changed_fraction: float = .05
    min_facing: float = .1
    min_alpha: float = .95
    require_identity: bool = True

    def __post_init__(self):
        for name, low, high in (("sampling_size", 16, 128), ("max_views", 1, 20),
                ("max_observations", 1, 8), ("max_references", 1, 8),
                ("max_total_pixels", 1, 4_194_304), ("max_samples", 1, 262_144),
                ("max_work", 1000, 50_000_000), ("max_regions", 1, 128),
                ("min_region_samples", 1, 16_384), ("min_region_extent", 1, 128), ("min_changed_pixels", 1, 16_384)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low},{high}].")
        if type(self.require_identity) is not bool:
            raise ValueError("require_identity must be a boolean.")
        for name in ("min_coverage", "color_tolerance", "max_changed_fraction", "min_facing", "min_alpha"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be finite in (0,1].")
        if (type(self.max_seconds) not in (int, float) or not math.isfinite(self.max_seconds)
                or not 0 < self.max_seconds <= 120):
            raise ValueError("Appearance deadline must be finite in (0,120].")

    def contract(self):
        checks = ("appearance.coverage", "appearance.color_consistency")
        if self.require_identity:
            checks += ("appearance.identity_assessment",)
        return DiagnosticPolicy("meshvenn.appearance_diagnostics", "1.0.0", fingerprint(asdict(self)), checks)
