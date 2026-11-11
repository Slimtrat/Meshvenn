"""Run the real preflight and qualify only the capability actually measured."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from core.diagnostic_contracts import (
    ArtifactReference, CameraDeclaration, CanonicalReference, ContentReference,
    DiagnosticReport, DiagnosticResolution, EngineVersion,
    Evidence, Finding, ViewRevision, ViewSetRevision,
)
from core.diagnostics_preflight import AlignmentAnchor, PreflightPolicy, RasterInput, ViewInput, analyze_preflight
from core.image_mask import BinaryMask

from . import CORPUS_VERSION, MANIFEST_SCHEMA_VERSION, QUALIFICATION_SCHEMA_VERSION
from .evidence import binary_alpha, difference_overlay
from .fixtures import canonical_json, sha256
from .scoring import aggregate, score_case, semantic_signature

DEFERRED = (
    ("D3", "geometry.cross_view_conflict", "geometry", "Cross-view reconstruction, part localization and fault attribution are not implemented/evaluated by this tranche."),
    ("D4", "appearance.identity_drift", "appearance", "No appearance or semantic identity evaluator ran."),
    ("D5", "correction.plan_available", "quality", "No localized correction planner ran."),
    ("D6", "iteration.acceptance", "quality", "No candidate generation, promotion or regression loop ran."),
    ("D7", "qualification.human_review", "quality", "Human-reviewed generated views, provider fidelity and end-to-end acceptance remain unqualified; issue #84 remains open."),
    ("D8", "quality.export_verified", "quality", "No GLB export/reload or accessible product acceptance ran."),
)


def implementation_provenance() -> dict:
    """Hash the actual imported authorities, including sibling-worktree sources.

    Public module identifiers are sufficient to audit the inputs. Absolute
    paths, machine/user names and repository dirtiness are not exported.
    """
    prefixes = ("core.diagnostic_contracts", "core.diagnostics_preflight", "core.projection_math",
                "scripts.diagnostic_corpus")
    authorities = {"core.projection_frame", "core.projection_alignment", "core.image_mask"}
    sources = {}
    for name, module in sorted(sys.modules.copy().items()):
        if name in authorities or any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
            path = getattr(module, "__file__", None)
            if not path or Path(path).suffix != ".py":
                raise ValueError(f"Cannot identify imported source for {name}")
            sources[name] = sha256(Path(path).read_bytes())
    entrypoint = Path(__file__).resolve().parents[1] / "qualify_diagnostics.py"
    sources["scripts.qualify_diagnostics"] = sha256(entrypoint.read_bytes())
    return {"source_sha256": dict(sorted(sources.items())), "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation()}


def qualification_identity(manifest_hash: str, implementation: dict, policies: list[dict]) -> str:
    return sha256(canonical_json({"schema_version": QUALIFICATION_SCHEMA_VERSION, "corpus_version": CORPUS_VERSION,
        "manifest_sha256": manifest_hash, "implementation": implementation, "policies": policies}))


def checked_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Corpus asset path escapes the corpus root")
    return path


def load_manifest(root: Path) -> tuple[dict, str]:
    manifest_data = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_data)
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION or manifest.get("corpus_version") != CORPUS_VERSION:
        raise ValueError("Unsupported corpus schema/version")
    if not manifest.get("cases") or len({c["case_id"] for c in manifest["cases"]}) != len(manifest["cases"]):
        raise ValueError("Corpus requires unique, nonempty cases")
    for case in manifest["cases"]:
        source = checked_path(root, case["truth"]["source_path"]).read_bytes()
        if sha256(source) != case["truth"]["source_sha256"] or source != canonical_json(case["truth"]["source"]):
            raise ValueError(f"Analytic source changed: {case['case_id']}")
        for variant in case["variants"]:
            for view in variant["views"]:
                for asset in view["assets"].values():
                    data = checked_path(root, asset["path"]).read_bytes()
                    if sha256(data) != asset["sha256"]:
                        raise ValueError(f"Corpus asset changed: {asset['path']}")
    return manifest, sha256(manifest_data)


def inputs_for_case(root: Path, case: dict, variant: dict, order: str = "canonical"):
    source_artifact = ArtifactReference("analytic-source", case["truth"]["source_sha256"], "application/json",
                                        "analytic-source.json")
    views, inputs, anchors, references = [], {}, [], []
    for record in variant["views"]:
        name = record["view_id"]
        assets = record["assets"]
        rasters = {role: RasterInput.from_path(checked_path(root, asset["path"])) for role, asset in assets.items()}
        def content(role):
            asset = assets[role]
            return ContentReference(asset["sha256"], asset["width"], asset["height"], asset["media_type"])
        declaration = record["declared_camera"]
        verified = declaration["verified"] and declaration["projection"] == "orthographic"
        camera = CameraDeclaration(declaration["projection"], declaration["azimuth_degrees"],
                                   declaration["elevation_degrees"], declaration["flip_x"], verified,
                                   source_artifact if verified else None)
        views.append(ViewRevision(name, 1, content("image"), content("mask"), camera, origin="rendered",
                                  origin_details="Original analytic synthetic fixture, not a documentary/human-validated image."))
        inputs[name] = ViewInput(rasters["image"], rasters["mask"])
        reference_id = f"ref_{name}"
        references.append(reference_id)
        reference_camera = CameraDeclaration("orthographic", declaration["azimuth_degrees"], 0, False, True, source_artifact)
        views.append(ViewRevision(reference_id, 1, content("reference"), None, reference_camera,
                                  role="reference", origin="rendered", origin_details="Independent projection of the frozen analytic source."))
        inputs[reference_id] = ViewInput(rasters["reference"])
        anchors.append(AlignmentAnchor(name, reference_id, source_artifact.sha256))
    canonical = CanonicalReference("analytic-canonical", 1,
                                   next(v.image for v in views if v.view_id == references[0]), True,
                                   tuple(references), source_artifact)
    ids = [view.view_id for view in views]
    if order == "reverse":
        ids.reverse()
    elif order == "rotate":
        ids = ids[1:] + ids[:1]
    elif order != "canonical":
        raise ValueError("Unknown view permutation")
    by_id = {view.view_id: view for view in views}
    view_set = ViewSetRevision(f"corpus-{case['case_id']}-{variant['resolution']}", 1,
                              tuple(by_id[name] for name in ids), canonical, tuple(ids))
    return view_set, {name: inputs[name] for name in ids}, tuple(anchors)


def complete_report(preflight: DiagnosticReport, *, engine_contract: bool = False,
                    implementation_fingerprint: str = "") -> DiagnosticReport:
    unknowns = tuple(Finding(f"unevaluated-{stage}", code, category, "info", "unknown",
                             f"{stage} has not been qualified.", reason=reason)
                     for stage, code, category, reason in DEFERRED)
    if engine_contract:
        unknowns += (Finding("engine-failure-specimen", "engine.native_execution", "engine", "error", "unknown",
                             "Engine failure contract specimen; native engine was not invoked.",
                             reason="Synthetic execution-state contract fixture; this checks representation of failure, not a real native failure run."),)
    policy = replace(preflight.policy, policy_id="meshvenn.corpus.analytic-subset", version=CORPUS_VERSION,
                     configuration_sha256=sha256(canonical_json({"preflight": preflight.policy.to_dict(), "deferred": DEFERRED})),
                     required_checks=tuple(sorted(set(preflight.policy.required_checks) | {finding.code for finding in unknowns})))
    assumptions = preflight.assumptions + ("Analytic synthetic truth only; no real-world or human-reviewed generated ground truth.",)
    if implementation_fingerprint:
        assumptions += ("qualification-implementation:" + implementation_fingerprint,)
    report = replace(preflight, findings=preflight.findings + unknowns,
                   engines=preflight.engines + (EngineVersion("diagnostic-corpus", CORPUS_VERSION),),
                   policy=policy, completion="failed" if engine_contract else "partial",
                   assumptions=assumptions)
    return replace(report, report_id="corpus-" + report.dependency_fingerprint[:20])


def execution_failure_report(view_set: ViewSetRevision, size: int, error: str, implementation_fingerprint="") -> DiagnosticReport:
    failure = Finding("corpus-execution-failed", "engine.preflight_execution", "engine", "error", "unknown",
                      "The real preflight could not complete; no diagnostic success is established.", reason=error)
    base = DiagnosticReport("corpus-execution-failed", view_set, (EngineVersion("meshvenn.preflight", "1.0.0"),),
                            PreflightPolicy().contract(), DiagnosticResolution(size, size), (failure,), completion="failed")
    return replace(complete_report(base, implementation_fingerprint=implementation_fingerprint), completion="failed")


def write_evidence(output: Path, variant: dict, inputs: dict, result) -> tuple[dict, ...]:
    """Persist real decoded comparisons and actual, unaccepted proposal mappings."""
    artifacts = []
    proposals = {proposal.view_id: proposal for proposal in result.proposals}
    for record in variant["views"]:
        name, size = record["view_id"], variant["resolution"]
        # These fixed names belong to this generated output; do not leave an old
        # proposal image looking like evidence for a later run with no proposal.
        for phase in ("before", "proposed"):
            (output / f"overlay-{name}-{phase}.png").unlink(missing_ok=True)
        observed = binary_alpha(inputs[name].mask or inputs[name].image)
        reference = binary_alpha(inputs[f"ref_{name}"].image)
        comparisons = [("before", observed)]
        if name in proposals:
            aligned = proposals[name].alignment.align_mask(BinaryMask(size, size, observed))
            comparisons.append(("proposed", aligned.values))
        for phase, mask in comparisons:
            data = difference_overlay(mask, reference, size)
            filename = f"overlay-{name}-{phase}.png"
            (output / filename).write_bytes(data)
            artifacts.append({"view_id": name, "phase": phase, "path": filename, "sha256": sha256(data),
                              "media_type": "image/png", "kind": "actual_input_vs_analytic_reference"})
    return tuple(artifacts)


def attach_evidence(report: DiagnosticReport, artifacts: tuple[dict, ...]) -> DiagnosticReport:
    findings = []
    for finding in report.findings:
        supplementary = []
        for artifact in artifacts:
            if artifact["view_id"] in finding.view_ids:
                identity = f"corpus-{artifact['view_id']}-{artifact['phase']}"
                supplementary.append(Evidence(identity, "artifact",
                    "Actual mask overlay: gray intersection, red reference-only, blue observed-only; proposed is unaccepted registration.",
                    (artifact["view_id"],), artifact=ArtifactReference(identity, artifact["sha256"], "image/png", artifact["path"])))
        findings.append(replace(finding, evidence=finding.evidence + tuple(supplementary)))
    return replace(report, findings=tuple(findings))


def proposal_observations(result, case: dict, size: int) -> dict:
    observations = []
    injection = case["injection"]
    for proposal in result.proposals:
        expected_scale = 1 / injection["parameter"] if injection["kind"] == "scale" else 1
        expected_u = -injection["parameter"] if injection["kind"] == "shift" else 0
        error = max(abs(proposal.alignment.offset_u - expected_u), abs(proposal.alignment.offset_v),
                    abs(proposal.alignment.scale - expected_scale))
        observations.append({"view_id": proposal.view_id, "alignment": proposal.alignment.as_dict(),
                             "before_iou": proposal.before_iou, "after_iou": proposal.after_iou,
                             "expected_inverse_alignment": {"offset_u": expected_u, "offset_v": 0, "scale": expected_scale},
                             "max_parameter_error": error, "parameter_tolerance": 3/(size-1),
                             "within_analytic_tolerance": error <= 3/(size-1)})
    return {"proposals": observations, "all_within_analytic_tolerance": all(o["within_analytic_tolerance"] for o in observations)}


def run_qualification(root: Path, output: Path, *, selected_cases: tuple[str, ...] = (), split="all",
                      resolutions: tuple[int, ...] = (128, 256), permutations=("canonical", "reverse", "rotate")) -> dict:
    started = perf_counter()
    implementation = implementation_provenance()
    implementation_fingerprint = sha256(canonical_json(implementation))
    manifest, manifest_hash = load_manifest(root)
    known_ids = {case["case_id"] for case in manifest["cases"]}
    if set(selected_cases) - known_ids:
        raise ValueError("Unknown requested case ID")
    if (not resolutions or not set(resolutions) <= {128,256} or len(set(resolutions)) != len(resolutions) or
            not permutations or permutations[0] != "canonical" or not set(permutations) <= {"canonical","reverse","rotate"} or
            len(set(permutations)) != len(permutations)):
        raise ValueError("Require unique supported resolutions and permutations, with canonical first")
    output.mkdir(parents=True, exist_ok=True)
    (output / "qualification.json").write_bytes(canonical_json({"schema_version": QUALIFICATION_SCHEMA_VERSION,
        "corpus_version": CORPUS_VERSION, "manifest_sha256": manifest_hash,
        "qualification_status": "unknown", "completion": "running"}))
    results = []
    sensitivity = []
    for case in manifest["cases"]:
        if (selected_cases and case["case_id"] not in selected_cases) or (split != "all" and case["split"] != split):
            continue
        base_signature, base_proposals = None, None
        for variant in case["variants"]:
            size = variant["resolution"]
            if size not in resolutions:
                continue
            case_started = perf_counter()
            directory = output / case["case_id"] / str(size)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "analytic-source.json").write_bytes(checked_path(root, case["truth"]["source_path"]).read_bytes())
            item = {"case_id": case["case_id"], "split": case["split"], "resolution": size,
                    "information_class": case["information_class"], "d3_d8": "unknown"}
            view_set = None
            try:
                view_set, inputs, anchors = inputs_for_case(root, case, variant)
                preflight_started = perf_counter()
                result = analyze_preflight(view_set, inputs, anchors=anchors)
                item["preflight_latency_seconds"] = perf_counter() - preflight_started
                findings = result.report.to_dict()["findings"]
                item["scoring"] = score_case(case["expected"], findings)
                signature = semantic_signature(findings)
                order_checks = []
                permutation_seconds = 0.0
                for permutation in permutations[1:]:
                    ids = list(view_set.input_order)
                    ids = list(reversed(ids)) if permutation == "reverse" else ids[1:] + ids[:1]
                    other_set = replace(view_set, input_order=tuple(ids))
                    other_inputs = {name: inputs[name] for name in ids}
                    other_anchors = tuple(reversed(anchors))
                    permutation_started = perf_counter()
                    other = analyze_preflight(other_set, other_inputs, anchors=other_anchors)
                    permutation_seconds += perf_counter() - permutation_started
                    same = semantic_signature(other.report.to_dict()["findings"]) == signature
                    same &= other.report.dependency_fingerprint == result.report.dependency_fingerprint
                    same &= [asdict(p) for p in other.proposals] == [asdict(p) for p in result.proposals]
                    order_checks.append({"permutation": permutation, "same_conclusions_dependencies_and_proposals": same})
                item["order_checks"] = order_checks
                item["permutation_latency_seconds"] = permutation_seconds
                item["proposal_observations"] = proposal_observations(result, case, size)
                proposals = {p.view_id: p.alignment.as_dict() for p in result.proposals}
                if base_signature is not None:
                    same_codes = signature == base_signature
                    differences = [abs(value - base_proposals[view_id][key]) for view_id, values in proposals.items()
                                   if view_id in base_proposals for key, value in values.items()]
                    max_difference = max(differences, default=0)
                    same_proposals = set(proposals) == set(base_proposals) and max_difference <= 3/(min(resolutions)-1)
                    sensitivity.append({"case_id": case["case_id"], "resolution": size, "same_conclusions": same_codes,
                                        "same_proposals_within_tolerance": same_proposals, "max_alignment_parameter_difference": max_difference,
                                        "tolerance": 3/(min(resolutions)-1)})
                else:
                    base_signature, base_proposals = signature, proposals
                artifacts = write_evidence(directory, variant, inputs, result)
                report = attach_evidence(complete_report(result.report,
                    engine_contract=case["injection"]["kind"] == "engine_failure_contract",
                    implementation_fingerprint=implementation_fingerprint), artifacts)
                encoded = report.to_json()
                decoded = DiagnosticReport.from_json(encoded)
                item["d1_roundtrip"] = decoded.to_json() == encoded
                item["downstream_checks_unknown"] = all(f.status == "unknown" for f in report.findings if f.code in {d[1] for d in DEFERRED})
                item["report_verification_status"] = report.verification_status.value
                item["report_completion"] = report.completion.value
                item["preflight_verification_status"] = result.report.verification_status.value
                item["preflight_dependency_fingerprint"] = result.report.dependency_fingerprint
                item["policy"] = result.report.policy.to_dict()
                item["report"] = f"{case['case_id']}/{size}/diagnostic-report.json"
                item["evidence"] = list(artifacts)
                (directory / "diagnostic-report.json").write_text(encoded + "\n", encoding="utf-8")
            except Exception as exc:
                # Runtime defects are qualification failures, never data success.
                item["error"] = f"{type(exc).__name__}: {exc}"
                if view_set is not None:
                    failure_report = execution_failure_report(view_set, size, item["error"], implementation_fingerprint)
                    item["report"] = f"{case['case_id']}/{size}/diagnostic-report.json"
                    item["report_completion"] = "failed"
                    item["report_verification_status"] = failure_report.verification_status.value
                    (directory / "diagnostic-report.json").write_text(failure_report.to_json() + "\n", encoding="utf-8")
            item["latency_seconds"] = perf_counter() - case_started
            (directory / "observations.json").write_bytes(canonical_json(item))
            results.append(item)
    if not results:
        raise ValueError("No cases selected")
    metrics = aggregate(results)
    valid = not metrics["failed_cases"] and all(r.get("d1_roundtrip") and r.get("downstream_checks_unknown") and
        r.get("proposal_observations", {}).get("all_within_analytic_tolerance") and
        all(c["same_conclusions_dependencies_and_proposals"] for c in r.get("order_checks", [])) for r in results)
    valid &= all(c["same_conclusions"] and c["same_proposals_within_tolerance"] for c in sensitivity)
    sources_unchanged = implementation_provenance() == implementation
    valid &= sources_unchanged
    complete_matrix = not selected_cases and split == "all" and set(resolutions) == {128,256} and set(permutations) == {"canonical","reverse","rotate"}
    d1_valid = all(r.get("d1_roundtrip") and r.get("downstream_checks_unknown") for r in results) and not metrics["execution_failures"]
    policies = [json.loads(value) for value in sorted({json.dumps(r["policy"], sort_keys=True) for r in results if "policy" in r})]
    summary = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION, "corpus_version": CORPUS_VERSION,
        "manifest_sha256": manifest_hash, "qualification_status": "pass" if valid else "fail",
        "implementation": implementation, "implementation_sources_unchanged_during_run": sources_unchanged,
        "qualification_identity": qualification_identity(manifest_hash, implementation, policies),
        "policies": policies,
        "latency": {"total_seconds": perf_counter() - started, "clock": "time.perf_counter",
                    "scope": "Local hash verification, decoding, real preflight/permutations, report serialization and evidence generation; not a product SLA."},
        "external_services": {"provider_calls": 0, "paid_api_cost": 0.0, "currency": "USD", "network_required": False},
        "scope": "D1/D2 analytic offline subset only; D3-D8, human/generative/provider/end-to-end acceptance UNKNOWN; #84 remains open",
        "complete_matrix": complete_matrix,
        "qualified_capabilities": ["common report roundtrip and unknown discipline", "real preflight input/camera/coverage checks", "bounded same-camera registration controls"] if valid and complete_matrix else [],
        "stage_results": {"D1": {"status": "pass" if d1_valid else "fail", "report_variants": len(results)},
                          "D2": {"status": "pass" if valid else "fail",
                                 "passing_case_variants": [f"{r['case_id']}/{r['resolution']}" for r in results if r.get("scoring", {}).get("passed_expectations") and not r.get("error")],
                                 "failing_case_variants": [f"{r['case_id']}/{r['resolution']}" for r in results if not r.get("scoring", {}).get("passed_expectations") or r.get("error")]}},
        "unevaluated": [{"stage": stage, "code": code, "status": "unknown", "reason": reason} for stage, code, _, reason in DEFERRED],
        "metrics": metrics, "by_split": {name: aggregate([r for r in results if r["split"] == name]) for name in ("calibration", "heldout")},
        "resolution_sensitivity": sensitivity, "cases": results,
        "calibration_policy": "Frozen engine defaults; no threshold fitting or heldout tuning performed by this command.",
        "evidence_legend": "gray=intersection; red=reference-only; blue=observed-only; white=background. Proposed overlays are unaccepted, derived by actual preflight proposals.",
    }
    (output / "qualification.json").write_bytes(canonical_json(summary))
    return summary
