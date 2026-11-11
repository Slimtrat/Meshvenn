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


def score_case(case: dict, observation: dict) -> dict:
    findings = observation.get("report", {}).get("findings", [])
    expected = case["expected"]
    assertions = []
    for requirement in expected["required"]:
        matches = [f for f in findings if f["code"] == requirement["code"] and f["status"] == requirement["status"]]
        assertions.append({"name": requirement["code"] + ":" + requirement["status"], "passed": bool(matches),
                           "kind": "required_signal"})
    conflicts = [f for f in findings if f["code"] == "geometry.cross_view_conflict" and f["status"] == "fail"]
    blame = [f for f in findings if any(a["kind"] == "regenerate_region" for a in f["proposed_actions"])]
    metrics = [v["metrics"] for v in observation.get("views", []) if v["metrics"].get("iou") is not None]
    for control in expected["controls"]:
        passed = False
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
            passed = any(r["status"] == "fail" and r["region"]["label"] == "identity_flag"
                         for m in metrics for r in m.get("important_regions", []))
            passed = passed or any(f["code"] == "geometry.detail_preservation" and f["status"] == "fail" and
                                   any(r["label"] == "identity_flag" for r in f["regions"]) for f in findings)
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
        assertions.append({"name": control, "passed": passed, "kind": "control"})
    failures = [item["name"] for item in assertions if not item["passed"]]
    return {"passed": not failures, "assertions": assertions, "failures": failures,
            "mean_iou": sum(m["iou"] for m in metrics) / len(metrics) if metrics else None,
            "abstentions": [{"code": f["code"], "view_ids": f["view_ids"], "reason": f["reason"]}
                            for f in findings if f["status"] == "unknown"]}
