"""Bounded static orthographic cross-view geometry diagnostics (D3)."""
from .backend import NativeGeometryBackend
from .engine import GeometryPolicy, analyze_geometry
from .models import (
    GeometryAttempt, GeometryExperiment, GeometryMetrics, GeometryPairComparison, GeometryProvenance, GeometryResult,
    MaskArtifact, RegionMeasurement, SequentialTraceStep, ViewGeometryResult, VolumeArtifact,
)

__all__ = ("GeometryPolicy", "NativeGeometryBackend", "analyze_geometry", "GeometryResult",
           "GeometryAttempt", "GeometryExperiment", "GeometryMetrics", "GeometryPairComparison", "GeometryProvenance", "MaskArtifact",
           "RegionMeasurement", "SequentialTraceStep", "ViewGeometryResult", "VolumeArtifact")
