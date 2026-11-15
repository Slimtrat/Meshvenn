"""Bounded, versioned offline correction planning policy."""
from dataclasses import asdict, dataclass
import math

from ..diagnostic_contracts.codec import fingerprint


@dataclass(frozen=True)
class CorrectionPolicy:
    max_plans: int = 64
    max_findings: int = 4096
    max_annotations: int = 128
    max_seconds: float = 20.
    min_region_pixels: int = 4
    min_region_extent: int = 2
    max_region_fraction: float = .35

    def __post_init__(self):
        for name,low,high in (("max_plans",1,128),("max_findings",1,8192),("max_annotations",1,128),
                ("min_region_pixels",1,65536),("min_region_extent",1,256)):
            value=getattr(self,name)
            if type(value) is not int or not low<=value<=high:
                raise ValueError(f"{name} must be an integer in [{low},{high}].")
        if type(self.max_seconds) not in (float,int) or not math.isfinite(self.max_seconds) or not 0<self.max_seconds<=120:
            raise ValueError("Correction planning deadline must be in (0,120].")
        if type(self.max_region_fraction) not in (float,int) or not math.isfinite(self.max_region_fraction) or not 0<self.max_region_fraction<=1:
            raise ValueError("The maximum edit fraction must be in (0,1].")

    @property
    def dependency_fingerprint(self):
        return fingerprint(asdict(self))
