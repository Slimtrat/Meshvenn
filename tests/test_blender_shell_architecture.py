from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BlenderShellArchitectureTests(unittest.TestCase):
    def test_production_modules_stay_below_500_lines(self) -> None:
        for package_name in ("properties", "operators", "ui"):
            for path in (ROOT / package_name).glob("*.py"):
                count = len(path.read_text(encoding="utf-8-sig").splitlines())
                self.assertLess(count, 500, f"{path} has {count} lines")

    def test_public_facades_keep_expected_symbols(self) -> None:
        expected = {
            "properties/groups.py": {
                "BPT_PG_ProjectionView", "BPT_PG_PipelineStageSettings",
                "BPT_PG_PipelineSettings", "BPT_PG_Settings",
                "PIPELINE_STAGE_DEFAULTS", "PIPELINE_STAGE_PROPERTY_NAMES",
            },
            "operators/projections.py": {
                "BPT_OT_LoadProjectionImage", "BPT_OT_ImportTurntableImages",
                "BPT_OT_AddProjection", "BPT_OT_RemoveProjection",
                "_extract_angle_from_name",
            },
            "operators/runtime.py": {
                "clear_pipeline_runtime_state", "get_last_pipeline_context",
                "get_last_pipeline_report", "_plan_through_stage",
            },
            "ui/drawers.py": {"ImplementationDrawersMixin"},
        }
        for relative_path, names in expected.items():
            tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8-sig"))
            visible = {
                alias.asname or alias.name
                for node in tree.body
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            visible.update(
                node.name for node in tree.body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            )
            self.assertTrue(names <= visible, f"{relative_path}: missing {names - visible}")


if __name__ == "__main__":
    unittest.main()
