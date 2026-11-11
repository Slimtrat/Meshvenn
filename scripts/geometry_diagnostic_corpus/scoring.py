"""Predeclared assertions, including healthy and metric-gaming controls."""
from __future__ import annotations


def semantic_signature(report: dict, *, include_bounds=True) -> list:
    """Order-independent conclusions, localization and suggested actions."""
    return sorted((finding["code"], finding["status"], tuple(sorted(finding["view_ids"])),
                   tuple(sorted((r["view_id"], r["label"], tuple(r.get("bounds") or ()) if include_bounds else ())
                                for r in finding["regions"])),
                   tuple(sorted((a["kind"], tuple(sorted(a["view_ids"])))
                                for a in finding["proposed_actions"])))
                  for finding in report["findings"])


def localization_sensitivity(baseline: dict, comparison: dict) -> dict:
    """Retain actual normalized bounds and validate stable named locations.

    The bound is the sum of the engine's two explicit raster/voxel numerical
    uncertainties plus half a sample from each raster. Residual components have
    no stable semantic identity across grids, so retain both sets and nearest
    box distances without pretending those are proven correspondences.
    """
    def normalized_error(record, view_id):
        view = next((v for v in record.get("views", []) if v["view_id"] == view_id), None)
        if view is None:
            return None
        size = view["expected"]["width"]
        return (view["resolution_tolerance_pixels"] + .5) / max(1, size - 1)

    def regions(record):
        result = {}
        for finding in record.get("report", {}).get("findings", []):
            for region in finding["regions"]:
                key = (finding["code"], region["view_id"], region["label"])
                result.setdefault(key, []).append({"status": finding["status"], "bounds": region["bounds"]})
        return result

    left, right = regions(baseline), regions(comparison)
    matched, unmatched = [], []
    for key in sorted(set(left) | set(right)):
        item = {"code": key[0], "view_id": key[1], "label": key[2],
                "baseline": left.get(key, []), "comparison": right.get(key, [])}
        if key not in left or key not in right:
            item["state"] = "unknown"
            item["reason"] = "This regional finding is absent at one resolution; no localization equivalence is asserted."
            unmatched.append(item)
            continue
        tolerance_left, tolerance_right = normalized_error(baseline, key[1]), normalized_error(comparison, key[1])
        tolerance = tolerance_left + tolerance_right if tolerance_left is not None and tolerance_right is not None else None
        a = [r["bounds"] for r in left[key] if r["bounds"] is not None]
        b = [r["bounds"] for r in right[key] if r["bounds"] is not None]
        error = max([min(max(abs(x-y) for x, y in zip(box, other)) for other in b) for box in a] +
                    [min(max(abs(x-y) for x, y in zip(box, other)) for other in a) for box in b]) if a and b else None
        item.update({"maximum_symmetric_nearest_bounds_delta": error, "normalized_tolerance": tolerance,
                     "state": "pass" if error is not None and tolerance is not None and error <= tolerance else
                              "fail" if error is not None and tolerance is not None else "unknown"})
        matched.append(item)
    residuals = []
    by_left = {v["view_id"]: v for v in baseline.get("views", [])}
    by_right = {v["view_id"]: v for v in comparison.get("views", [])}
    for view_id in sorted(set(by_left) | set(by_right)):
        for kind in ("missing_regions", "extraneous_regions"):
            a = [r["bounds"] for r in by_left.get(view_id, {}).get("metrics", {}).get(kind, [])]
            b = [r["bounds"] for r in by_right.get(view_id, {}).get("metrics", {}).get(kind, [])]
            nearest = max([min(max(abs(x-y) for x, y in zip(box, other)) for other in b) for box in a] +
                          [min(max(abs(x-y) for x, y in zip(box, other)) for other in a) for box in b]) if a and b else None
            residuals.append({"view_id": view_id, "kind": kind, "baseline_bounds": a, "comparison_bounds": b,
                              "symmetric_nearest_bounds_delta": nearest,
                              "semantic_component_correspondence": "unknown"})
    return {"coordinate_space": "normalized bottom-left image bounds",
            "tolerance_policy": "Sum of both measured projection uncertainty bounds plus half a sample from each raster",
            "matched_regions": matched, "unmatched_regions": unmatched, "residual_components": residuals,
            "matched_bounds_within_tolerance": all(item["state"] != "fail" for item in matched),
            "unmatched_localization_is_unknown": bool(unmatched)}


def score_case(case: dict, observation: dict) -> dict:
    findings = observation.get("report", {}).get("findings", [])
    expected = case["expected"]
    assertions = []
    for requirement in expected["required"]:
        matches = [f for f in findings if f["code"] == requirement["code"] and f["status"] == requirement["status"]]
        localized = requirement["code"] == "camera.unsupported" or (requirement["code"] == "geometry.cross_view_conflict" and
            case["injection"] in ("extend_front_arm", "pair_conflict"))
        if localized:
            matches = [f for f in matches if "front" in f["view_ids"]]
        assertions.append({"name": requirement["code"] + ":" + requirement["status"], "passed": bool(matches),
                           "kind": "required_signal"})
    conflicts = [f for f in findings if f["code"] == "geometry.cross_view_conflict" and f["status"] == "fail"]
    blame = [f for f in findings if any(a["kind"] == "regenerate_region" for a in f["proposed_actions"])]
    metrics = [v["metrics"] for v in observation.get("views", []) if v["metrics"].get("iou") is not None]
    for control in expected["controls"]:
        passed = False
        sources = []
        if control == "nonempty":
            passed = observation.get("occupied_count", 0) > 0
        elif control == "empty":
            passed = observation.get("occupied_count") == 0
        elif control == "no_conflict":
            # An engine doing nothing must not satisfy healthy controls.
            expected_views = {view["view_id"] for view in case["variants"][0]["views"]}
            measured_pass = {view_id for f in findings if f["code"] == "geometry.cross_view_conflict" and f["status"] == "pass"
                             for view_id in f["view_ids"]}
            unresolved = [f for f in findings if f["code"] == "geometry.cross_view_conflict" and f["status"] in ("unknown", "fail")]
            passed = expected_views <= measured_pass and not unresolved
        elif control == "no_blame":
            passed = not blame and bool(findings)
        elif control == "large_valid_reduction":
            steps = observation.get("trace", [])
            passed = any(s["before"] > 0 and s["after"] > 0 and
                         1 - s["after"] / s["before"] >= expected["large_reduction_minimum"] for s in steps)
        elif control == "good_mean_iou":
            passed = bool(metrics) and sum(m["iou"] for m in metrics) / len(metrics) >= expected["mean_iou_good_minimum"]
        elif control == "important_region_failure":
            if any(r["status"] == "fail" and r["region"]["label"] == "identity_flag"
                   for m in metrics for r in m.get("important_regions", [])):
                sources.append("actual_native_voxel_reprojection")
            for pair in observation.get("pair_comparisons", []):
                if any(r["status"] == "fail" and r["region"]["label"] == "identity_flag" for r in pair["metrics"].get("important_regions", [])):
                    kind = "actual_independent_canonical_input_comparison" if pair.get("mapping") == "independent-canonical-same-camera" else "actual_calibrated_antipodal_input_comparison"
                    if kind not in sources:
                        sources.append(kind)
            passed = bool(sources)
        elif control == "canonical_eligible_front":
            # Eligibility means independently supported localization for user
            # review, never an automatically executed generative correction.
            passed = any(f["code"] == "geometry.reference_conflict" and f["status"] == "fail" and
                         {"front", "ref_front"} <= set(f["view_ids"]) for f in findings)
        elif control == "native_rejection":
            probe = observation.get("native_probe", {})
            passed = probe.get("state") == "native_rejected" and probe.get("dll_api_executed") is True and probe.get("native_error_code", 0) != 0
        else:
            raise ValueError("Unknown frozen control: " + control)
        assertions.append({"name": control, "passed": passed, "kind": "control", "evidence_sources": sources})
    failures = [item["name"] for item in assertions if not item["passed"]]
    healthy_control = "no_conflict" in expected["controls"]
    return {"passed": not failures, "assertions": assertions, "failures": failures,
            "unexpected_geometry_abstentions": [{"code": f["code"], "view_ids": f["view_ids"], "reason": f["reason"]}
                for f in findings if healthy_control and f["code"] == "geometry.cross_view_conflict" and f["status"] == "unknown"],
            "unexpected_geometry_failures": [{"code": f["code"], "view_ids": f["view_ids"]}
                for f in findings if healthy_control and f["code"].startswith("geometry.") and f["status"] == "fail"],
            "mean_iou": sum(m["iou"] for m in metrics) / len(metrics) if metrics else None,
            "abstentions": [{"code": f["code"], "view_ids": f["view_ids"], "reason": f["reason"]}
                            for f in findings if f["status"] == "unknown"]}
