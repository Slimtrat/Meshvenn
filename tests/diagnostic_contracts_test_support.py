from __future__ import annotations

from core.diagnostic_contracts import (
    ArtifactReference, CameraDeclaration, CanonicalReference, ContentReference,
    DiagnosticPolicy, DiagnosticReport, DiagnosticResolution, EngineVersion,
    Evidence, Finding, Measurement, ViewRevision, ViewSetRevision,
)


def source(digest="a", width=64, height=48):
    return ContentReference(digest * 64, width, height, "image/png")


def view_set():
    proof = ArtifactReference("camera-proof", "c" * 64, "application/json", "proof/camera.json")
    camera = CameraDeclaration("orthographic", 0, 0, verified=True, verification_evidence=proof)
    return ViewSetRevision("mascot", 2, (
        ViewRevision("front", 3, source(), source("b"), camera, origin="user"),
        ViewRevision("side", 1, source("d"), source("e"), CameraDeclaration("orthographic", 90, 0))),
        CanonicalReference("identity", 2, source("f"), validated=True, view_ids=("front",)))


def observed_finding(*, status="pass", required=True):
    return Finding("mask-front", "input.empty_mask", "input", "info", status,
                   "The front mask contains foreground pixels.", ("front",),
                   evidence=(Evidence("foreground-front", "observation", "Decoded binary mask area.",
                                      ("front",), measurements=(Measurement("foreground_pixels", 768, "pixel"),)),),
                   required=required)


def report(**changes):
    values = dict(report_id="report-2", view_set=view_set(),
                  engines=(EngineVersion("preflight", "1.0"),),
                  policy=DiagnosticPolicy("static-asset", "1", "1" * 64, ("input.empty_mask",)),
                  resolution=DiagnosticResolution(64, 48), findings=(observed_finding(),),
                  assumptions=("Orthographic cameras are declared, not inferred.",))
    values.update(changes)
    return DiagnosticReport(**values)
