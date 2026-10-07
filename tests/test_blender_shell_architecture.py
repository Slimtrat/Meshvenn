from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BlenderShellArchitectureTests(unittest.TestCase):
    def test_modular_export_does_not_prepare_or_initialize_source(self) -> None:
        path = ROOT / "implementations/glb_export/implementation.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        methods = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        calls = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                 for node in ast.walk(methods["execute"])
                 if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))}
        self.assertIn("require_prepared_source", calls)
        self.assertFalse(calls & {"prepare_authored_source", "stage_authored_scene_catalogue",
                                 "_initial_static_catalogue", "context_from_authored_scene"})

    def test_modular_authoring_controls_have_one_owner(self) -> None:
        exporter = (ROOT / "implementations/glb_export/implementation.py").read_text(encoding="utf-8-sig")
        authoring = (ROOT / "operators/modular_authoring.py").read_text(encoding="utf-8-sig")
        for operator in ("bpt.prepare_modular_source", "bpt.load_modular_face_ownership",
                         "bpt.assign_modular_faces", "bpt.save_modular_face_ownership"):
            self.assertIn(operator, authoring)
            self.assertNotIn(operator, exporter)

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
