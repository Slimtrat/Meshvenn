"""Durable local regeneration loop around a trusted host port."""

from dataclasses import asdict
import json, os
from pathlib import Path
import time

from .models import Asset, Assessment, Budget, policy_fingerprint
from .session_lock import session_lock

RECIPES = ("local-018", "local-028", "radial-200", "bone-heat")


class HumanoidLoop:
    """Host port: detect(), source_digest(), baseline(), regenerate(), evaluate(), verify().

    The host owns paths/execution. Source and candidate artifacts remain immutable.
    Failed/unknown candidates never replace a source, even when their rank improves.
    """

    def __init__(self, port, workspace, *, budget=None, clock=time.time):
        self.port = port
        self.workspace = Path(workspace)
        self.budget = budget or Budget()
        self.clock = clock
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.path = self.workspace / "session.json"

    def _save(self, state):
        temporary = self.path.with_suffix(".pending")
        temporary.write_text(
            json.dumps(state, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def run(self, *, resume=False, cancel=None):
        with session_lock(self.workspace / "session.lock"):
            return self._run(resume=resume, cancel=cancel)

    def _run(self, *, resume=False, cancel=None):
        source = self.port.source_digest()
        fingerprint = policy_fingerprint(self.budget)
        if self.path.exists():
            if not resume:
                raise ValueError("Session exists; resume explicitly")
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                state["source_sha256"] != source
                or state["policy_sha256"] != fingerprint
            ):
                raise ValueError("Source or frozen quality policy changed")
            if state["status"] not in ("running", "cancelled"):
                self._verify_selection(state)
                return state
            state["status"] = "running"
        else:
            state = dict(
                schema_version=1,
                profile="native-humanoid-deformation-v1",
                policy_sha256=fingerprint,
                source_sha256=source,
                budget=asdict(self.budget),
                started_at=self.clock(),
                elapsed_seconds=0.0,
                status="running",
                attempts=[],
                selected=None,
                best=None,
                quality_certification="unknown",
                consumer_acceptance="unknown",
            )
            state["detection"] = self.port.detect()
            if state["detection"].get("applicable") is not True:
                state["status"] = "not_applicable"
                self._save(state)
                return state
            self._save(state)

        def stop_reason():
            if self.port.source_digest() != state["source_sha256"]:
                raise ValueError("Source changed during analysis")
            state["elapsed_seconds"] = max(
                state["elapsed_seconds"], self.clock() - state["started_at"]
            )
            if state["elapsed_seconds"] >= self.budget.max_elapsed_seconds:
                return "budget_exhausted"
            if cancel and cancel():
                return "cancelled"
            return None

        if "baseline" not in state:
            reason = stop_reason()
            if reason:
                state["status"] = reason
                self._save(state)
                return state
            try:
                baseline = self.port.baseline(cancel=cancel)
                assessment = self.port.evaluate(baseline, cancel=cancel)
            except InterruptedError:
                state["status"] = "cancelled"
                self._save(state)
                return state
            except Exception as exc:
                state["status"] = "analysis_failed"
                state["error"] = dict(type=type(exc).__name__, message=str(exc)[:2000])
                self._save(state)
                return state
            self._check_assessment(assessment, baseline)
            state["baseline"] = assessment.to_dict()
            state["best"] = state["baseline"]
            self._save(state)
        best = self._assessment(state["best"])
        if not best.preservation_passed:
            state["status"] = "invalid_source"
            self._save(state)
            return state
        if best.passed:
            return self._finish(state, best, stop_reason())
        stagnant = state.get("stagnation", 0)
        for index, recipe in enumerate(RECIPES[: self.budget.max_attempts]):
            reason = stop_reason()
            if reason:
                state["status"] = reason
                self._save(state)
                return state
            if stagnant >= self.budget.max_stagnation:
                state["status"] = "stagnated"
                break
            if index < len(state["attempts"]) and state["attempts"][index][
                "status"
            ] in ("evaluated", "failed"):
                continue
            row = dict(
                id=f"candidate-{index+1:02d}", recipe=recipe, status="generating"
            )
            if index == len(state["attempts"]):
                state["attempts"].append(row)
            else:
                row = state["attempts"][index]
            self._save(state)
            try:
                candidate = self.port.regenerate(row["id"], recipe, cancel=cancel)
                self.port.verify(candidate)
                row.update(status="evaluating", asset=asdict(candidate))
                self._save(state)
                reason = stop_reason()
                if reason:
                    state["status"] = reason
                    self._save(state)
                    return state
                assessment = self.port.evaluate(candidate, cancel=cancel)
                self._check_assessment(assessment, candidate)
                reason = stop_reason()
                if reason:
                    state["status"] = reason
                    self._save(state)
                    return state
                self.port.verify(candidate)
                row.update(status="evaluated", assessment=assessment.to_dict())
                if assessment.preservation_passed and assessment.rank < best.rank:
                    best = assessment
                    state["best"] = best.to_dict()
                    stagnant = 0
                else:
                    stagnant += 1
                state["stagnation"] = stagnant
                self._save(state)
                if assessment.passed:
                    return self._finish(state, assessment, stop_reason())
            except InterruptedError:
                state["status"] = "cancelled"
                self._save(state)
                return state
            except Exception as exc:
                row.update(
                    status="failed",
                    error=dict(type=type(exc).__name__, message=str(exc)[:2000]),
                )
                stagnant += 1
                state["stagnation"] = stagnant
                self._save(state)
        if state["status"] == "running":
            state["status"] = "budget_exhausted"
        self._save(state)
        return state

    def _check_assessment(self, assessment, asset):
        if not isinstance(assessment, Assessment) or assessment.asset != asset:
            raise ValueError("Assessment targets a different asset")

    @staticmethod
    def _assessment(value):
        return Assessment(
            Asset(**value["asset"]), value["measurements"], value["evidence"]
        )

    def _verify_selection(self, state):
        if state["selected"] is not None:
            selected = Asset(**state["selected"])
            best = self._assessment(state["best"])
            if (
                state["status"] != "checks_passed"
                or not best.passed
                or best.asset != selected
            ):
                raise ValueError("Selection has no matching passing assessment")
            self.port.verify(selected)
        if self.port.source_digest() != state["source_sha256"]:
            raise ValueError("Source changed during the loop")

    def _finish(self, state, assessment, reason):
        if reason:
            state["status"] = reason
        else:
            self.port.verify(assessment.asset)
            if self.port.source_digest() != state["source_sha256"]:
                raise ValueError("Source changed during the loop")
            state.update(
                status="checks_passed",
                selected=asdict(assessment.asset),
                best=assessment.to_dict(),
            )
        self._save(state)
        return state
