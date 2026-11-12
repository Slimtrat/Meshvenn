"""Read-only surface-aware appearance evidence, independent of Blender/providers."""
from .surface import SurfaceMesh
from .policy import AppearancePolicy, AppearanceViewSettings
from .models import AppearanceResult, AppearanceRegionAnchor
from .engine import analyze_appearance
from .semantics import VisionAnalyzer

__all__ = ("SurfaceMesh", "AppearancePolicy", "AppearanceViewSettings", "AppearanceResult",
           "AppearanceRegionAnchor", "analyze_appearance", "VisionAnalyzer")
