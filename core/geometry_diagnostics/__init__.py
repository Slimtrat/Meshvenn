"""Bounded static orthographic cross-view geometry diagnostics (D3)."""
from .backend import NativeGeometryBackend
from .engine import GeometryPolicy, analyze_geometry
from .models import (
    GeometryExperiment, GeometryMetrics, GeometryProvenance, GeometryResult,
    MaskArtifact, RegionMeasurement, SequentialTraceStep, ViewGeometryResult, VolumeArtifact,
)

__all__ = ("GeometryPolicy", "NativeGeometryBackend", "analyze_geometry", "GeometryResult",
           "GeometryExperiment", "GeometryMetrics", "GeometryProvenance", "MaskArtifact",
           "RegionMeasurement", "SequentialTraceStep", "ViewGeometryResult", "VolumeArtifact")
