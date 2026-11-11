"""Pure deterministic multiview input preparation; no Blender or credentials."""
from .rasters import RasterInput, ViewInput
from .registration import AlignmentAnchor, AlignmentProposal, CertifiedProjectionInput
from .engine import (
    PreflightPolicy, PreflightResult, PreflightAcceptance, analyze_preflight,
    accept_alignment, accept_alignments,
)

__all__ = (
    "RasterInput", "ViewInput", "AlignmentAnchor", "AlignmentProposal",
    "CertifiedProjectionInput", "PreflightPolicy", "PreflightResult", "PreflightAcceptance",
    "analyze_preflight", "accept_alignment", "accept_alignments",
)
