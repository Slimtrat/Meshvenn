"""Evaluate original rasters through the actual isolated native D3 engine."""
from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from enum import Enum
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

from core.diagnostic_contracts import (ArtifactReference, CameraDeclaration, CanonicalReference,
    ContentReference, DiagnosticPolicy, DiagnosticReport, DiagnosticResolution, EngineVersion,
    Evidence, Finding, Measurement, Region, ViewRevision, ViewSetRevision)
from core.diagnostics_preflight import RasterInput, ViewInput
from scripts.diagnostic_corpus.evidence import difference_overlay
from scripts.diagnostic_corpus.fixtures import canonical_json, sha256
from . import CORPUS_VERSION, FROZEN_MANIFEST_SHA256, SCHEMA_VERSION
from .scoring import localization_sensitivity, score_case, semantic_signature


def checked_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Corpus path escapes its root")
    return path


def load_manifest(root: Path) -> tuple[dict, str]:
    data = (root / "manifest.json").read_bytes()
    manifest = json.loads(data)
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("corpus_version") != CORPUS_VERSION:
        raise ValueError("Unsupported geometry corpus")
    if sha256(data) != FROZEN_MANIFEST_SHA256:
        raise ValueError("Frozen geometry manifest changed; use a reviewed new corpus version")
    ids = [case["case_id"] for case in manifest["cases"]]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Corpus requires unique cases")
    for case in manifest["cases"]:
        records = [case["source"]] + [asset for variant in case["variants"] for view in variant["views"] for asset in view["assets"].values()]
        for record in records:
            if sha256(checked_path(root, record["path"]).read_bytes()) != record["sha256"]:
                raise ValueError("Corpus evidence changed: " + record["path"])
    return manifest, sha256(data)


def inputs_for_case(root: Path, case: dict, variant: dict, order: str):
    proof = ArtifactReference("analytic-camera-proof", case["source"]["sha256"], "application/json", "analytic-source.json")
    views, inputs, references = [], {}, []
    for record in variant["views"]:
        name, assets = record["view_id"], record["assets"]
        rasters = {role: RasterInput.from_path(checked_path(root, asset["path"])) for role, asset in assets.items()}
        def content(role):
            asset = assets[role]
            return ContentReference(asset["sha256"], asset["width"], asset["height"], asset["media_type"])
        declaration = record["declared_camera"]
        verified = declaration["projection"] == "orthographic" and declaration["verified"]
        camera = CameraDeclaration(declaration["projection"], declaration["azimuth_degrees"],
                                   declaration["elevation_degrees"], False, verified, proof if verified else None)
        views.append(ViewRevision(name, 1, content("image"), content("mask"), camera, origin="rendered",
                                  origin_details="Original analytic synthetic observation; no human/generated-image validation."))
        inputs[name] = ViewInput(rasters["image"], rasters["mask"])
        if case["canonical"]:
            ref_id = "ref_" + name
            references.append(ref_id)
            camera = CameraDeclaration("orthographic", declaration["azimuth_degrees"], 0, False, True, proof)
            views.append(ViewRevision(ref_id, 1, content("reference"), None, camera, role="reference", origin="rendered",
                                      origin_details="Independent projection of original source; never derived from an observation."))
            inputs[ref_id] = ViewInput(rasters["reference"])
    canonical = CanonicalReference("analytic-canonical", 1,
        next(view.image for view in views if view.view_id in references), True, tuple(references), proof) if references else None
    ids = [view.view_id for view in views]
    if order == "reverse":
        ids.reverse()
    elif order == "rotate":
        ids = ids[1:] + ids[:1]
    elif order != "canonical":
        raise ValueError("Unknown input permutation")
    by_id = {view.view_id: view for view in views}
    revision = ViewSetRevision("geometry-" + case["case_id"] + "-" + str(variant["raster_resolution"]),
                               1, tuple(by_id[name] for name in ids), canonical, tuple(ids))
    regions = tuple(Region(r["view_id"], r["label"], tuple(r["bounds"])) for r in case["regions"])
    return revision, {name: inputs[name] for name in ids}, regions


def jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return {"sha256": sha256(value), "byte_count": len(value)}
    if isinstance(value, Path):
        return value.name
    if is_dataclass(value):
        # Actual masks/volumes have hashed, replayable artifacts. Avoid copying
        # their hex payload into every experiment and the aggregate JSON.
        if type(value).__name__ in ("MaskArtifact", "VolumeArtifact"):
            return {f.name: jsonable(getattr(value, f.name)) for f in fields(value) if f.name != "values_hex"} | {
                "byte_count": len(value.values)}
        return {f.name: jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(v) for v in value]
    return value


def implementation_provenance(native_library: Path) -> dict:
    prefixes = ("core.geometry_diagnostics", "core.diagnostics_preflight", "core.diagnostic_contracts",
                "core.projection_math", "core.native_bridge", "scripts.geometry_diagnostic_corpus", "scripts.diagnostic_corpus")
    authorities = {"core.native_loader", "core.image_mask", "core.projection_frame", "core.projection_alignment"}
    sources = {}
    for name, module in sorted(sys.modules.copy().items()):
        if name in authorities or any(name == p or name.startswith(p + ".") for p in prefixes):
            path = getattr(module, "__file__", None)
            if path and Path(path).suffix == ".py":
                sources[name] = sha256(Path(path).read_bytes())
    # Workers execute in children, so their authorities may never appear in
    # this process's sys.modules. Hash the actual selected package directories.
    for prefix in prefixes:
        module = sys.modules.get(prefix)
        package_file = getattr(module, "__file__", None)
        if not package_file or Path(package_file).name != "__init__.py":
            continue
        directory = Path(package_file).parent
        for path in directory.rglob("*.py"):
            relative = path.relative_to(directory).with_suffix("")
            suffix = ".".join(relative.parts)
            name = prefix if suffix == "__init__" else prefix + "." + suffix.removesuffix(".__init__")
            sources[name] = sha256(path.read_bytes())
    entry = Path(__file__).parents[1] / "qualify_geometry_diagnostics.py"
    sources["scripts.qualify_geometry_diagnostics"] = sha256(entry.read_bytes())
    return {"source_sha256": sources, "native_library_sha256": sha256(native_library.read_bytes()),
            "python_executable_sha256": sha256(Path(sys.executable).read_bytes()),
            "python_version": platform.python_version(), "python_implementation": platform.python_implementation(),
            "platform": {"system": platform.system(), "machine": platform.machine()}}


def complete_report(report: DiagnosticReport, manifest_hash: str, implementation: dict) -> DiagnosticReport:
    deferred = (("appearance.identity_drift", "No D4 appearance or identity evaluation ran."),
                ("correction.plan_available", "No D5 generative correction planning/execution was qualified."),
                ("iteration.acceptance", "No D6 accepted iteration or promotion was qualified."),
                ("qualification.human_review", "D7 human/provider/end-to-end acceptance remains open, including issue #84."),
                ("quality.export_verified", "No D8 GLB delivery, hidden-surface or topology certification ran."))
    known = {finding.code for finding in report.findings}
    unknowns = tuple(Finding("deferred-" + code.replace(".", "-"), code,
        "appearance" if code.startswith("appearance.") else "quality", "info", "unknown",
        "Later-stage acceptance remains unknown.", reason=reason) for code, reason in deferred if code not in known)
    policy = replace(report.policy, policy_id="meshvenn.geometry-corpus", version=CORPUS_VERSION,
        configuration_sha256=sha256(canonical_json({"engine": report.policy.to_dict(), "manifest": manifest_hash,
                                                    "implementation": implementation})),
        required_checks=tuple(sorted(set(report.policy.required_checks) | {f.code for f in unknowns})))
    result = replace(report, findings=report.findings + unknowns, policy=policy,
                     engines=report.engines + (EngineVersion("geometry-corpus", CORPUS_VERSION),),
                     completion="partial" if report.completion == "complete" else report.completion)
    return replace(result, report_id="geometry-corpus-" + result.dependency_fingerprint[:20])


def probe_report(view_set, raster: int, probe: dict) -> DiagnosticReport:
    evidence = Evidence("real-native-rejection", "execution", "Real native API failure path, not a mocked orchestration result.",
                        measurements=(Measurement("dll_api_executed", int(probe.get("dll_api_executed") is True), "boolean"),
                                      Measurement("native_error_code", probe.get("native_error_code", -1), "code"),
                                      Measurement("elapsed_seconds", probe["elapsed_seconds"], "second")))
    finding = Finding("native-rejection-probe", "engine.native_failure", "engine", "error", "unknown",
                      "Bounded native API rejection probe; no geometry fidelity result.", evidence=(evidence,),
                      reason="A genuine DLL API rejection checks operational handling only; reconstruction quality was not evaluated.")
    policy = DiagnosticPolicy("native-api-rejection-probe", "1", sha256(canonical_json({"resolution": 0, "hard_timeout_seconds": 5})),
                              ("engine.native_failure",))
    return DiagnosticReport("native-rejection-probe", view_set, (EngineVersion("native-api-probe", "1"),),
                            policy, DiagnosticResolution(raster, raster), (finding,), completion="failed")


def execution_failure_report(view_set, policy, error: dict) -> DiagnosticReport:
    finding = Finding("geometry-execution-failure", "engine.geometry_execution", "engine", "error", "unknown",
                      "The actual geometry analysis raised an unexpected exception; no quality success is established.",
                      reason=error["error_type"] + ": " + error["message"])
    return DiagnosticReport("geometry-execution-failure", view_set, (EngineVersion("geometry-corpus", CORPUS_VERSION),),
                            policy.contract(), DiagnosticResolution(policy.resolution, policy.resolution, policy.resolution, "voxel"),
                            (finding,), completion="failed")


def write_evidence(destination: Path, result, *, prefix="", scope="selected-result") -> tuple[dict, ...]:
    artifacts = []
    volumes = [("full", result.volume)] + [(experiment.experiment_id, experiment.volume) for experiment in result.experiments]
    for phase, volume in volumes:
        if volume is None:
            continue
        filename = prefix + "native-volume-" + phase + ".bin"
        (destination / filename).write_bytes(volume.values)
        artifacts.append({"view_id": None, "experiment_id": phase, "path": filename,
                          "sha256": sha256(volume.values), "volume_artifact_sha256": volume.sha256,
                          "width": volume.width, "depth": volume.depth, "height": volume.height,
                          "occupied_count": volume.occupied_count, "bounds": volume.bounds,
                          "media_type": "application/octet-stream", "kind": "actual_native_volume_binary_occupancy"})
    comparisons = [("full", result.views)] + [(experiment.experiment_id, experiment.views) for experiment in result.experiments]
    for phase, views in comparisons:
        for view in views:
            expected, actual = view.expected, view.reprojected
            if expected.width != expected.height or expected.width != actual.width or expected.height != actual.height:
                raise ValueError("Overlay requires actual same-sized square masks")
            data = difference_overlay(actual.values, expected.values, expected.width)
            filename = prefix + "overlay-" + phase + "-" + view.view_id + ".png"
            (destination / filename).write_bytes(data)
            artifacts.append({"view_id": view.view_id, "experiment_id": phase, "path": filename,
                              "sha256": sha256(data), "media_type": "image/png",
                              "kind": "actual_native_voxel_reprojection_vs_original_input"})
    for pair in getattr(result, "pair_comparisons", ()):
        filename = prefix + "overlay-input-pair-" + pair.target_view_id + "-" + pair.counterpart_view_id + ".png"
        data = difference_overlay(pair.counterpart.values, pair.expected.values, pair.expected.width)
        (destination / filename).write_bytes(data)
        kind = "actual_independent_canonical_input_comparison" if pair.mapping == "independent-canonical-same-camera" else "actual_calibrated_antipodal_input_comparison"
        artifacts.append({"view_id": pair.target_view_id, "counterpart_view_id": pair.counterpart_view_id,
                          "experiment_id": "pair-" + pair.target_view_id + "-" + pair.counterpart_view_id,
                          "path": filename, "sha256": sha256(data), "media_type": "image/png",
                          "kind": kind, "mapping": pair.mapping})
    return tuple(artifact | {"evidence_scope": scope} for artifact in artifacts)


def attach_evidence(report: DiagnosticReport, artifacts: tuple[dict, ...], *, scope="selected-result") -> DiagnosticReport:
    findings = []
    for finding in report.findings:
        extra = tuple(Evidence("geometry-overlay-" + str(i), "artifact",
            "Actual independent canonical comparison, separate from voxel evidence: gray intersection, red observation-only, blue reference-only."
            if a["kind"] == "actual_independent_canonical_input_comparison" else
            "Actual calibrated antipodal input comparison, separate from voxel evidence: gray intersection, red target-only, blue counterpart-only."
            if a["kind"] == "actual_calibrated_antipodal_input_comparison" else
            "Actual native voxel reprojection: gray intersection, red input-only, blue reconstruction-only.",
            (a["view_id"],), artifact=ArtifactReference("native-overlay-" + str(i), a["sha256"], "image/png", a["path"]))
            for i, a in enumerate(artifacts) if a.get("evidence_scope", "selected-result") == scope and a["view_id"] in finding.view_ids and
            (a["experiment_id"] == "full" or a["kind"] in ("actual_calibrated_antipodal_input_comparison", "actual_independent_canonical_input_comparison")))
        if finding.code == "engine.provenance":
            extra += tuple(Evidence("attempt-report-" + str(i), "artifact",
                "Actual preserved native attempt report, including its own resolution, unknowns, failures and budget deltas.",
                artifact=ArtifactReference("attempt-report-" + str(i), artifact["sha256"], "application/json", artifact["path"]))
                for i, artifact in enumerate(artifacts) if artifact["kind"] == "actual_native_attempt_report")
        findings.append(replace(finding, evidence=finding.evidence + extra))
    return replace(report, findings=tuple(findings))


def preserve_attempts(destination: Path, result, manifest_hash: str, implementation: dict) -> tuple[list[dict], tuple[dict, ...]]:
    """Persist every native attempt without replacing the coarse first result."""
    snapshots, all_artifacts = [], []
    for index, attempt in enumerate(getattr(result, "attempts", ()), 1):
        scope = f"attempt-{index:02d}-n{attempt.resolution}"
        artifacts = write_evidence(destination, attempt, prefix=scope + "-", scope=scope)
        report = complete_report(attach_evidence(attempt.report, artifacts, scope=scope), manifest_hash, implementation)
        serialized = report.to_json()
        filename = scope + "-diagnostic-report.json"
        (destination / filename).write_text(serialized, encoding="utf-8")
        report_artifact = {"view_id": None, "experiment_id": scope, "path": filename,
                           "sha256": sha256((destination / filename).read_bytes()), "media_type": "application/json",
                           "kind": "actual_native_attempt_report", "evidence_scope": scope, "resolution": attempt.resolution}
        snapshot = jsonable(attempt)
        snapshot.update({"attempt_index": index, "report": report.to_dict(), "artifacts": artifacts + (report_artifact,),
                         "contract_roundtrip_passed": DiagnosticReport.from_json(serialized).to_json() == serialized})
        snapshots.append(snapshot)
        all_artifacts.extend(artifacts + (report_artifact,))
    return snapshots, tuple(all_artifacts)


def attempt_accounting(result) -> dict:
    """Verify the new attempt/provenance contract without changing truth labels."""
    attempts = getattr(result, "attempts", ())
    if not attempts:
        return {"applicable": False, "passed": True, "checks": [],
                "reason": "This result has no attempt contract; retry behavior is not qualified by this observation."}
    checks = []
    def check(name, passed, observed):
        checks.append({"name": name, "passed": bool(passed), "observed": jsonable(observed)})
    resolutions = tuple(attempt.resolution for attempt in attempts)
    provenance = result.provenance
    check("at_most_two_attempts", 1 <= len(attempts) <= 2, len(attempts))
    check("original_requested_resolution_preserved", resolutions[0] == result.requested_resolution,
          {"requested": result.requested_resolution, "attempts": resolutions})
    check("single_n64_retry", len(attempts) == 1 or resolutions[1] == 64 and resolutions[0] < 64, resolutions)
    check("selected_attempt_resolution", result.actual_resolution == resolutions[-1] == result.report.resolution.width == provenance.resolution,
          {"actual": result.actual_resolution, "attempts": resolutions, "report": result.report.resolution.width,
           "provenance": provenance.resolution})
    check("attempted_resolutions", tuple(provenance.attempted_resolutions) == resolutions, provenance.attempted_resolutions)
    for index, attempt in enumerate(attempts, 1):
        check(f"attempt_{index}_resolution", attempt.report.resolution.width == attempt.resolution and
              (attempt.volume is None or attempt.volume.width == attempt.resolution),
              {"resolution": attempt.resolution, "report": attempt.report.resolution.width,
               "volume": attempt.volume.width if attempt.volume is not None else None})
    for field, budget, maximum in (("native_sessions_reserved", "native_session_budget", 24),
                                   ("native_applications_reserved", "native_application_budget", 220),
                                   ("native_voxel_test_capacity", "native_voxel_test_budget", 57_671_680),
                                   ("python_work_reserved", "python_work_budget", 8_000_000_000)):
        total = sum(getattr(attempt.provenance, field) for attempt in attempts)
        observed, limit = getattr(provenance, field), getattr(provenance, budget)
        check(field + "_shared_budget", total == observed and 0 <= observed <= limit <= maximum,
              {"sum_attempt_deltas": total, "reported_total": observed, "shared_budget": limit, "maximum_contract_budget": maximum})
    for field in ("completed_experiments", "native_projection_applications"):
        total = sum(getattr(attempt.provenance, field) for attempt in attempts)
        check(field + "_aggregate", total == getattr(provenance, field),
              {"sum_attempt_deltas": total, "reported_total": getattr(provenance, field)})
    native_total = sum(attempt.provenance.native_elapsed_seconds for attempt in attempts)
    check("native_elapsed_aggregate", abs(native_total - provenance.native_elapsed_seconds) <= 1e-6,
          {"sum_attempt_seconds": native_total, "reported_total": provenance.native_elapsed_seconds})
    elapsed_total = sum(attempt.provenance.elapsed_seconds for attempt in attempts)
    check("attempt_elapsed_within_total", elapsed_total <= provenance.elapsed_seconds + 1e-6,
          {"sum_attempt_seconds": elapsed_total, "reported_total": provenance.elapsed_seconds,
           "shared_deadline_seconds": provenance.deadline_seconds})
    return {"applicable": True, "passed": all(item["passed"] for item in checks), "checks": checks}


def native_rejection(native_library: Path) -> dict:
    started = perf_counter()
    try:
        child = subprocess.run([sys.executable, "-m", "scripts.geometry_diagnostic_corpus.native_probe", str(native_library)],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=5, check=False)
        try:
            result = json.loads(child.stdout)
        except (ValueError, TypeError):
            result = {"state": "worker_failure", "dll_api_executed": False, "protocol_valid": False}
        result.update({"returncode": child.returncode, "stderr_sha256": sha256(child.stderr.encode()),
                       "worker_stdout_sha256": sha256(child.stdout.encode())})
    except subprocess.TimeoutExpired:
        result = {"state": "worker_timeout", "dll_api_executed": None}
    result.update({"elapsed_seconds": perf_counter() - started, "hard_timeout_seconds": 5,
                   "mocked": False, "geometry_quality_evaluated": False})
    return result


def real_worker_deadline(backend, inputs) -> dict:
    """Exercise an actual child deadline separately from analysis preparation."""
    from core.image_mask import BinaryMask
    from core.native_bridge import NativeProjection
    raster = inputs["front"].mask
    mask = BinaryMask(raster.width, raster.height,
                      bytes(int(raster.rgba[i] >= .1) for i in range(3, len(raster.rgba), 4)))
    started = perf_counter()
    batch = backend.run((("front", NativeProjection(mask, 0)),), resolution=32,
                        input_order=("front",), timeout=.02, thread_count=1)
    return {"state": batch.state, "termination": batch.termination,
            "worker_started": batch.termination.startswith("terminated_deadline"),
            "native_completion_known": bool(batch.experiments), "completed_experiments": len(batch.experiments),
            "library_sha256": batch.library_sha256, "timeout_seconds": .02,
            "elapsed_seconds": perf_counter() - started, "mocked": False,
            "geometry_quality_evaluated": False}


def run_qualification(root: Path, output: Path, *, native_library: Path, selected_cases=(), split="all", quick=False) -> dict:
    from core.geometry_diagnostics import GeometryPolicy, NativeGeometryBackend, analyze_geometry
    # Load all native adapter sources before capturing authority fingerprints.
    from core.native_bridge import NativeCore  # noqa: F401
    started = perf_counter()
    native_library = native_library.resolve(strict=True)
    manifest, manifest_hash = load_manifest(root)
    if selected_cases and set(selected_cases) - {case["case_id"] for case in manifest["cases"]}:
        raise ValueError("Unknown selected geometry case")
    cases = [case for case in manifest["cases"] if (not selected_cases or case["case_id"] in selected_cases) and
             (split == "all" or case["split"] == split)]
    if not cases:
        raise ValueError("Selection contains no cases")
    policy_default = GeometryPolicy()
    implementation = implementation_provenance(native_library)
    identity = sha256(canonical_json({"manifest": manifest_hash, "implementation": implementation,
                                     "policy_defaults": jsonable(policy_default)}))
    # Each invocation preserves its own directory; later fixes never erase an initial failure.
    output.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while True:
        run_dir = output / "runs" / (identity[:16] + "-" + str(attempt))
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            attempt += 1
    records, order_checks, sensitivity = [], [], []
    backend = NativeGeometryBackend(library_path=native_library)
    for case in cases:
        case_records = []
        operational = case["injection"] in ("deadline", "native_invalid_resolution")
        configurations = manifest["execution_plan"]["configurations"][:1] if quick or operational else manifest["execution_plan"]["configurations"]
        for configuration in configurations:
            raster, voxel = configuration["raster"], configuration["voxel"]
            variant = next(v for v in case["variants"] if v["raster_resolution"] == raster)
            orders = ("canonical",) if quick or operational or configuration != configurations[0] else tuple(manifest["execution_plan"]["orders"])
            for order in orders:
                destination = run_dir / case["case_id"] / f"r{raster}-v{voxel}-{order}"
                destination.mkdir(parents=True)
                record = {"case_id": case["case_id"], "split": case["split"], "raster_resolution": raster,
                          "voxel_resolution": voxel, "order": order, "path": destination.relative_to(output).as_posix()}
                case_started = perf_counter()
                if case["injection"] == "native_invalid_resolution":
                    record["native_probe"] = native_rejection(native_library)
                    view_set, _inputs, _regions = inputs_for_case(root, case, variant, order)
                    report = complete_report(probe_report(view_set, raster, record["native_probe"]), manifest_hash, implementation)
                    record["report"] = report.to_dict()
                    (destination / "diagnostic-report.json").write_text(report.to_json(), encoding="utf-8")
                else:
                    view_set, inputs, regions = inputs_for_case(root, case, variant, order)
                    policy = replace(policy_default, resolution=voxel, reprojection_size=raster,
                                     max_seconds=.001 if case["injection"] == "deadline" else manifest["execution_plan"]["max_seconds_per_analysis"])
                    record["policy"] = jsonable(policy)
                    record["policy_sha256"] = sha256(canonical_json(record["policy"]))
                    if case["injection"] == "deadline":
                        record["native_worker_probe"] = real_worker_deadline(backend, inputs)
                    try:
                        result = analyze_geometry(view_set, inputs, policy=policy, backend=backend, regions=regions)
                        attempts, attempt_artifacts = preserve_attempts(destination, result, manifest_hash, implementation)
                        artifacts = write_evidence(destination, result) + attempt_artifacts
                        report = complete_report(attach_evidence(result.report, artifacts), manifest_hash, implementation)
                        serialized = report.to_json()
                        record["contract_roundtrip_passed"] = DiagnosticReport.from_json(serialized).to_json() == serialized
                        (destination / "diagnostic-report.json").write_text(serialized, encoding="utf-8")
                        record.update({"report": report.to_dict(), "views": jsonable(result.views),
                            "pair_comparisons": jsonable(getattr(result, "pair_comparisons", ())),
                            "experiments": jsonable(result.experiments), "trace": jsonable(result.trace),
                            "engine_provenance": jsonable(result.provenance), "artifacts": artifacts,
                            "attempts": attempts, "attempt_accounting": attempt_accounting(result),
                            "requested_voxel_resolution": getattr(result, "requested_resolution", voxel) or voxel,
                            "effective_voxel_resolution": getattr(result, "actual_resolution", 0) or result.provenance.resolution,
                            "occupied_count": result.volume.occupied_count if result.volume is not None else None})
                    except Exception as exc:
                        # Preserve unexpected engine failures as failures, never substitute a fake backend.
                        record["execution_failure"] = {"error_type": type(exc).__name__, "message": str(exc)}
                        report = complete_report(execution_failure_report(view_set, policy, record["execution_failure"]),
                                                 manifest_hash, implementation)
                        record["report"] = report.to_dict()
                        (destination / "diagnostic-report.json").write_text(report.to_json(), encoding="utf-8")
                record["elapsed_seconds"] = perf_counter() - case_started
                record["score"] = score_case(case, record)
                if record.get("execution_failure") or record.get("contract_roundtrip_passed") is False:
                    record["score"]["passed"] = False
                    record["score"]["failures"].append("execution_or_contract_failure")
                if record.get("attempt_accounting", {}).get("passed") is False or any(not attempt["contract_roundtrip_passed"] for attempt in record.get("attempts", [])):
                    record["score"]["passed"] = False
                    record["score"]["failures"].append("native_attempt_contract_failure")
                if case["injection"] == "deadline" and not record.get("native_worker_probe", {}).get("worker_started"):
                    record["score"]["passed"] = False
                    record["score"]["failures"].append("actual_worker_deadline_not_observed")
                (destination / "observation.json").write_bytes(canonical_json(record))
                source = checked_path(root, case["source"]["path"]).read_bytes()
                (destination / "analytic-source.json").write_bytes(source)
                records.append(record)
                case_records.append(record)
                print(f"{case['case_id']} r{raster} v{voxel} {order}: {'pass' if record['score']['passed'] else 'FAIL'} {record['score']['failures']}", flush=True)
        baseline = next(r for r in case_records if r["order"] == "canonical")
        for record in case_records:
            if record["order"] != "canonical":
                comparable = "report" in baseline and "report" in record
                order_checks.append({"case_id": case["case_id"], "order": record["order"],
                    "passed": comparable and semantic_signature(baseline["report"]) == semantic_signature(record["report"]),
                    "sequential_trace_excluded_from_conclusions": True})
            elif record is not baseline and "report" in record:
                sensitivity.append({"case_id": case["case_id"], "baseline": [baseline["raster_resolution"], baseline["voxel_resolution"]],
                    "comparison": [record["raster_resolution"], record["voxel_resolution"]],
                    "baseline_effective_voxel_resolution": baseline.get("effective_voxel_resolution", baseline["voxel_resolution"]),
                    "comparison_effective_voxel_resolution": record.get("effective_voxel_resolution", record["voxel_resolution"]),
                    "baseline_attempt_resolutions": [attempt["resolution"] for attempt in baseline.get("attempts", [])],
                    "comparison_attempt_resolutions": [attempt["resolution"] for attempt in record.get("attempts", [])],
                    "same_conclusions": "report" in baseline and semantic_signature(baseline["report"], include_bounds=False) == semantic_signature(record["report"], include_bounds=False),
                    "both_satisfy_frozen_expectations": baseline["score"]["passed"] and record["score"]["passed"],
                    "localization": localization_sensitivity(baseline, record),
                    "baseline_mean_iou": baseline["score"]["mean_iou"], "comparison_mean_iou": record["score"]["mean_iou"]})
    unchanged = implementation == implementation_provenance(native_library) and manifest_hash == load_manifest(root)[1]
    metrics = {}
    for partition in ("calibration", "heldout"):
        selected = [r for r in records if r["split"] == partition]
        metrics[partition] = {"evaluations": len(selected), "passed": sum(r["score"]["passed"] for r in selected),
            "failed": sum(not r["score"]["passed"] for r in selected),
            "assertions": sum(len(r["score"]["assertions"]) for r in selected),
            "missed_assertions": sum(len(r["score"]["failures"]) for r in selected),
            "execution_failures": sum("execution_failure" in r for r in selected),
            "native_attempts": sum(len(r.get("attempts", [])) for r in selected),
            "native_retries": sum(max(0, len(r.get("attempts", [])) - 1) for r in selected),
            "attempt_contract_failures": sum(not r.get("attempt_accounting", {}).get("passed", True) for r in selected),
            "passing_controls": sum(a["passed"] for r in selected for a in r["score"]["assertions"] if a["kind"] == "control"),
            "missing_controls": sum(not a["passed"] for r in selected for a in r["score"]["assertions"] if a["kind"] == "control"),
            "unexpected_geometry_abstentions_on_healthy_controls": sum(len(r["score"]["unexpected_geometry_abstentions"]) for r in selected),
            "unexpected_geometry_failures_on_healthy_controls": sum(len(r["score"]["unexpected_geometry_failures"]) for r in selected),
            "abstentions": sum(len(r["score"]["abstentions"]) for r in selected)}
    complete = not selected_cases and split == "all" and not quick
    passed = unchanged and all(r["score"]["passed"] for r in records) and all(c["passed"] for c in order_checks)
    # Sensitivity is an acceptance check against frozen expectations; retain actual conclusion changes too.
    passed = passed and all(c["both_satisfy_frozen_expectations"] and c["localization"]["matched_bounds_within_tolerance"] for c in sensitivity)
    summary = {"schema_version": SCHEMA_VERSION, "corpus_version": CORPUS_VERSION, "manifest_sha256": manifest_hash,
        "qualification_identity": identity, "implementation": implementation, "authorities_unchanged": unchanged,
        "qualification_status": "pass" if passed else "fail", "complete_matrix": complete,
        "qualified_scope": "D3 analytic native subset" if passed and complete else "No full D3 matrix qualification established",
        "scope_limits": manifest["scope"], "metrics": metrics, "records": records, "order_checks": order_checks,
        "resolution_sensitivity": sensitivity, "elapsed_seconds": perf_counter() - started,
        "provider_calls": 0, "network_calls": 0, "paid_cost": 0,
        "run_path": run_dir.relative_to(output).as_posix(), "previous_attempts_retained": True}
    data = canonical_json(summary)
    (run_dir / "qualification.json").write_bytes(data)
    (output / "qualification.json").write_bytes(data)
    return summary
