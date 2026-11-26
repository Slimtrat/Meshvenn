from pathlib import Path
import hashlib, json, sys, tempfile, unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from meshvenn_humanoid import Asset, Assessment, Budget, HumanoidLoop
from meshvenn_humanoid.models import LIMITS
from meshvenn_humanoid.session_lock import session_lock


def assessment(asset, *, bad=False, unknown=False, changed=False):
    values = {n: 0.0 if d == "max" else 1.0 for n, (d, _) in LIMITS.items()}
    if bad:
        values["proximal_link_error"] = 0.3
    if unknown:
        values["elbow_area_retention"] = None
    if changed:
        values["source_structure_changes"] = 1
    return Assessment(
        asset, values, {"simulation": "unit test port, not character qualification"}
    )


class Port:
    def __init__(self, results=None):
        self.assets = {}
        self.generated = []
        self.results = results or {}
        self.sha = "a" * 64
        self.applicable = True
        self.clock = None

    def source_digest(self):
        return self.sha

    def detect(self):
        return {"applicable": self.applicable}

    def baseline(self, **kwargs):
        return self.regenerate("baseline", "preserve")

    def regenerate(self, name, recipe, **kwargs):
        if name not in self.assets:
            self.generated.append(name)
            self.assets[name] = Asset(name, hashlib.sha256(name.encode()).hexdigest())
        return self.assets[name]

    def evaluate(self, asset, **kwargs):
        return assessment(
            asset, **self.results.get(asset.id, {"bad": asset.id == "baseline"})
        )

    def verify(self, asset):
        if self.assets[asset.id] != asset:
            raise ValueError("tampered")


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def test_bad_baseline_regenerates_and_selects_only_measured_passing_asset(self):
        port = Port()
        result = HumanoidLoop(port, self.path).run()
        self.assertEqual(result["status"], "checks_passed")
        self.assertEqual(result["selected"]["id"], "candidate-01")
        self.assertEqual(result["quality_certification"], "unknown")
        self.assertEqual(len(result["attempts"]), 1)

    def test_unknown_never_selects_even_when_error_improves(self):
        port = Port({f"candidate-{i:02d}": {"unknown": True} for i in range(1, 5)})
        result = HumanoidLoop(port, self.path).run()
        self.assertIsNone(result["selected"])

    def test_changed_source_surface_cannot_be_promoted(self):
        port = Port({f"candidate-{i:02d}": {"changed": True} for i in range(1, 5)})
        result = HumanoidLoop(port, self.path).run()
        self.assertIsNone(result["selected"])
        self.assertEqual(result["best"]["asset"]["id"], "baseline")

    def test_nonhumanoid_does_not_generate_anything(self):
        port = Port()
        port.applicable = False
        result = HumanoidLoop(port, self.path).run()
        self.assertEqual(result["status"], "not_applicable")
        self.assertEqual(port.generated, [])

    def test_healthy_baseline_is_not_regenerated(self):
        port = Port({"baseline": {}})
        result = HumanoidLoop(port, self.path).run()
        self.assertEqual(result["selected"]["id"], "baseline")
        self.assertEqual(port.generated, ["baseline"])

    def test_attempt_budget_stops_unresolved_failures(self):
        port = Port({f"candidate-{i:02d}": {"bad": True} for i in range(1, 5)})
        result = HumanoidLoop(port, self.path, budget=Budget(max_attempts=1)).run()
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertIsNone(result["selected"])

    def test_resume_checks_source_and_policy_and_reverifies_selected_bytes(self):
        port = Port()
        loop = HumanoidLoop(port, self.path)
        loop.run()
        self.assertEqual(loop.run(resume=True)["status"], "checks_passed")
        port.sha = "b" * 64
        with self.assertRaises(ValueError):
            loop.run(resume=True)

    def test_cancel_then_resume_preserves_elapsed_budget(self):
        port = Port()
        now = [0.0]
        loop = HumanoidLoop(port, self.path, clock=lambda: now[0])
        self.assertEqual(loop.run(cancel=lambda: True)["status"], "cancelled")
        now[0] = 181.0
        result = loop.run(resume=True)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertIsNone(result["selected"])

    def test_missing_or_nonfinite_measurements_cannot_pass(self):
        asset = Asset("baseline", "a" * 64)
        with self.assertRaises(ValueError):
            Assessment(asset, {}, {})
        value = assessment(asset).measurements
        value["proximal_link_error"] = float("nan")
        with self.assertRaises(ValueError):
            Assessment(asset, value, {})

    def test_tampered_terminal_selection_is_rejected(self):
        port = Port()
        loop = HumanoidLoop(port, self.path)
        loop.run()
        file = self.path / "session.json"
        state = json.loads(file.read_text())
        state["selected"] = state["baseline"]["asset"]
        file.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            loop.run(resume=True)

    def test_analysis_exception_is_persisted_without_selection(self):
        port = Port()

        def fail(*a, **kw):
            raise ValueError("Unmeasurable fixture")

        port.evaluate = fail
        result = HumanoidLoop(port, self.path).run()
        self.assertEqual(result["status"], "analysis_failed")
        self.assertIsNone(result["selected"])
        self.assertEqual(
            json.loads((self.path / "session.json").read_text())["error"]["type"],
            "ValueError",
        )

    def test_concurrent_worker_cannot_modify_the_journal(self):
        with session_lock(self.path / "session.lock"):
            with self.assertRaisesRegex(ValueError, "Another worker"):
                HumanoidLoop(Port(), self.path).run()
        self.assertFalse((self.path / "session.json").exists())
        self.assertEqual(
            HumanoidLoop(Port(), self.path).run()["status"], "checks_passed"
        )
