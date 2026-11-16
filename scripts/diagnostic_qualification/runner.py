"""Reproduce evidence locally. This module never dispatches a generation request."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid

from .archive import import_attempt, verify_archive
from .measure import write_comparison
from .presentation import render_page
from .report import assemble_report, canonical
from .review import import_review, review_status

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "tests/fixtures/diagnostics/provider-v1"
ARCHIVE = ROOT / "tests/fixtures/diagnostics/provider-attempt-v1"


def review_template(packet):
    return {"schema_version": 1, "review_id": "human_" + packet["packet_sha256"][:16],
            "packet_sha256": packet["packet_sha256"], "scope": "image_review",
            "image_sha256s": sorted(packet["roles"].get("after", [])),
            "glb_sha256s": sorted(packet["roles"].get("glb", [])),
            "reviewer": {"kind": "unknown", "name": None, "experience": "none", "non_3d": True, "attested": False},
            "state": "pending", "reviewed_at": None, "tasks": [],
            "limitations": ["A completed human attestation and task observations have not been supplied."]}


def _bound_comparison(packet, archive, reference, destination):
    """The selected before/reference/mask must belong to the frozen 3D fixture."""
    assets = {a["asset_id"]: a for a in packet["assets"]}
    required = {"before", "healthy", "mask", "fixture_manifest"}
    if not required <= assets.keys():
        return None
    manifest = json.loads((reference / "manifestfixture.json").read_bytes())
    pinned = {a["path"]: a["sha256"] for a in manifest["assets"]}
    expected = {"before": pinned["target-wrong-badge-transparent.png"],
                "healthy": pinned["reference-front-transparent.png"], "mask": pinned["badge-edit-mask.png"],
                "fixture_manifest": hashlib.sha256((reference / "manifestfixture.json").read_bytes()).hexdigest()}
    for name, digest in expected.items():
        if assets[name]["sha256"] != digest:
            raise ValueError("Attempt does not refer to the frozen original fixture: " + name)
    after = [a for a in packet["assets"] if a["role"] == "after"]
    if len(after) != 1:
        return None
    objects = archive / "objects"
    return write_comparison(objects / assets["healthy"]["sha256"], objects / assets["before"]["sha256"],
                            objects / after[0]["sha256"], objects / assets["mask"]["sha256"], destination)


def run_evidence(output: Path, *, native_library=None, selection=None, archive=None, attempt=None,
                 reference=REFERENCE, review=None, verify_only=False) -> dict:
    from .reference import verify_fixture
    reference = Path(reference)
    run = Path(output) / "runs" / uuid.uuid4().hex
    run.mkdir(parents=True, exist_ok=False)
    errors = []
    ref = packet = comparison = human = None
    corpora = {"status": "unknown", "all_full_matrices_passed": False, "reason": "Integrity-only replay; no diagnostic matrix executed."}
    pictures, downloads = [], []
    archive_path = Path(archive) if archive else ARCHIVE
    try:
        ref = verify_fixture(reference)
        ref = dict(ref, status="pass", evidence_mode="verified_archived_fresh_import_proof",
                   fresh_blender_reload_this_command=False, corrected_glb=False)
    except (OSError, ValueError) as exc:
        errors.append({"stage": "reference", "error": type(exc).__name__, "message": str(exc)})
    if not verify_only:
        from .corpora import run_corpora
        try:
            corpora = run_corpora(run / "corpora", native_library=native_library, selection=selection)
        except (OSError, ValueError) as exc:
            errors.append({"stage": "corpora", "error": type(exc).__name__, "message": str(exc)})
    try:
        if attempt:
            archive_path = run / "attempt"
            packet = import_attempt(Path(attempt), archive_path)
        elif archive_path.exists():
            packet = verify_archive(archive_path)
        elif archive:
            raise ValueError("The explicitly requested archive does not exist.")
        if packet:
            packet = dict(packet, outcome=packet["execution"]["outcome"])
            glbs = [a for a in packet["assets"] if a["role"] == "glb"]
            if not ref or len(glbs) != 1 or glbs[0]["asset_id"] != "reference_glb" or glbs[0]["sha256"] != ref["source_glb_sha256"]:
                if ref:
                    ref = dict(ref, status="unknown", attempt_glb_binding="fail")
                raise ValueError("The offered GLB is not bound to the exact independently verified reference reload.")
            ref = dict(ref, attempt_glb_binding="pass", attempt_packet_sha256=packet["packet_sha256"])
            if ref:
                comparison = _bound_comparison(packet, archive_path, reference, run / "pixel-preservation.png")
            human = import_review(Path(review), archive_path, run / "human-review") if review else review_status(archive_path)
            labels = {"healthy": "Référence attendue — badge bleu, rendu du GLB original", "before": "1. Avant — badge rose à corriger"}
            for role, label in (("before", labels["before"]), ("after", "2. Résultat brut de l’outil — à contrôler"), ("reference", labels["healthy"])):
                selected = [a for a in packet["assets"] if a["role"] == role and a["media_type"] == "image/png"]
                if role == "reference":
                    selected = [a for a in selected if a["asset_id"] == "healthy"]
                pictures.extend((label, archive_path / "objects" / a["sha256"]) for a in selected)
            for asset in packet["assets"]:
                if asset["role"] == "glb":
                    target = run / (asset["asset_id"] + ".glb")
                    target.write_bytes((archive_path / "objects" / asset["sha256"]).read_bytes())
                    downloads.append(("Télécharger le GLB de référence — " + asset["sha256"][:12], target))
            if comparison and comparison.get("overlay"):
                pictures.append(("Vert : masque demandé ; rouge : pixels modifiés ailleurs", run / comparison["overlay"]["path"]))
    except (OSError, ValueError) as exc:
        errors.append({"stage": "attempt_or_review", "error": type(exc).__name__, "message": str(exc)})
        packet = None
    report = assemble_report(corpora, attempt=packet, comparison=comparison, reference=ref, review=human)
    report.pop("report_sha256")
    report["technical_errors"] = errors
    execution_failed = any(r.get("technical_status") in ("failed", "timed_out") for r in corpora.get("results", []))
    report["technical_status"] = "failed" if errors or execution_failed or corpora.get("status") == "fail" else "completed"
    if errors:
        report["qualification_status"] = "fail"
    report["report_sha256"] = hashlib.sha256(canonical(report)).hexdigest()
    (run / "report.json").write_bytes(canonical(report))
    downloads.append(("Télécharger le rapport JSON", run / "report.json"))
    render_page(run / "review.html", report, pictures=pictures, downloads=downloads,
                review_template=review_template(packet) if packet and packet["execution"]["outcome"] == "completed" else None)
    return {"run_path": run, "report": report}
