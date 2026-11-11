"""Observed-vs-expected scoring; UNKNOWN is tracked separately from success."""

from __future__ import annotations

from collections import Counter


def score_case(expected: dict, findings: list[dict]) -> dict:
    """Score actual findings, never labels or generated fixture counts.

    Required observations include their verification state and, for local checks,
    their view localization. Declared admissible secondary findings are neutral;
    they cannot earn a true positive or hide an explicitly forbidden action.
    """
    signals = [finding for finding in findings if finding["status"] in ("fail", "unknown")]
    by_code = {code: [finding for finding in signals if finding["code"] == code]
               for code in {finding["code"] for finding in signals}}
    target = expected["target_view"]
    matched, misses, localization_misses = [], [], []
    for code in expected["required_codes"]:
        candidates = [finding for finding in by_code.get(code, [])
                      if finding["status"] == expected["required_statuses"][code]]
        if target and code not in ("coverage.insufficient",) and candidates and not any(target in finding.get("view_ids", []) for finding in candidates):
            localization_misses.append(code)
            candidates = []
        (matched if candidates else misses).append(code)
    allowed = set(expected["required_codes"] + expected["permitted_codes"])
    unexpected_findings = [finding for finding in signals if finding["code"] not in allowed or
        (target and finding["code"] != "coverage.insufficient" and target not in finding.get("view_ids", [])) or
        (finding["code"] in expected["required_statuses"] and finding["status"] != expected["required_statuses"][finding["code"]])]
    unexpected = sorted({finding["code"] for finding in unexpected_findings})
    forbidden = sorted(set(expected["forbidden_codes"]) & set(by_code))
    unexpected = sorted(set(unexpected + forbidden))
    controls = expected.get("pass_requirements", [])
    missed_controls = [control for control in controls if not any(finding["code"] == control["code"] and
        finding["status"] == "pass" and (control["view_id"] is None or control["view_id"] in finding.get("view_ids", [])) for finding in findings)]
    counts = Counter(finding["status"] for finding in findings)
    return {
        "true_positive_findings": len(matched), "false_positive_findings": len(unexpected_findings),
        "missed_findings": len(misses), "matched_expected_codes": matched,
        "missed_expected_codes": misses, "unexpected_codes": unexpected,
        "forbidden_codes_observed": forbidden, "localization_misses": localization_misses,
        "status_counts": dict(sorted(counts.items())),
        "abstained_codes": sorted({finding["code"] for finding in signals if finding["status"] == "unknown"}),
        "passed_control_checks": len(controls) - len(missed_controls), "missed_control_checks": missed_controls,
        "observed_signals": [{"code": finding["code"], "status": finding["status"], "view_ids": finding.get("view_ids", [])} for finding in signals],
        "passed_expectations": not misses and not unexpected and not missed_controls,
    }


def semantic_signature(findings: list[dict]) -> list:
    """Compare conclusions/localization; floating raster measurements are separate."""
    return sorted((finding["code"], finding["status"], tuple(sorted(finding.get("view_ids", [])))) for finding in findings)


def aggregate(results: list[dict]) -> dict:
    counts = Counter({key: 0 for key in ("true_positive_findings", "false_positive_findings", "missed_findings",
        "execution_failures", "failed_cases", "abstentions", "passed_control_checks", "missed_control_checks")})
    for result in results:
        score = result.get("scoring", {})
        for key in ("true_positive_findings", "false_positive_findings", "missed_findings"):
            counts[key] += score.get(key, 0)
        counts["execution_failures"] += bool(result.get("error"))
        counts["failed_cases"] += not score.get("passed_expectations", False) or bool(result.get("error"))
        counts["abstentions"] += len(score.get("abstained_codes", []))
        counts["passed_control_checks"] += score.get("passed_control_checks", 0)
        counts["missed_control_checks"] += len(score.get("missed_control_checks", []))
    tp, fp, miss = (counts[key] for key in ("true_positive_findings", "false_positive_findings", "missed_findings"))
    return {**dict(counts), "evaluated_variants": len(results),
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + miss) if tp + miss else None}
