"""Pure deterministic multiview input preparation; no Blender or credentials."""
from .rasters import RasterInput, ViewInput
from .registration import AlignmentAnchor, AlignmentProposal, CertifiedProjectionInput
from .engine import PreflightPolicy, PreflightResult, analyze_preflight, accept_alignment

__all__ = (
    "RasterInput", "ViewInput", "AlignmentAnchor", "AlignmentProposal",
    "CertifiedProjectionInput", "PreflightPolicy", "PreflightResult",
    "analyze_preflight", "accept_alignment",
)
