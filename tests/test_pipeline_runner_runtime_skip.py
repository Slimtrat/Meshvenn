from pipeline_runner_test_support import *


class PipelineRunnerRuntimeSkipTests(unittest.TestCase):
    def test_optional_skip_propagates_and_independent_export_continues(self) -> None:
        registry = PipelineRegistry()
        input_implementation = InputImplementation()
        geometry = GeometryImplementation()
        rig = FakeImplementation(
            identifier="auto-rig",
            stage=PipelineStage.RIG,
            result_state=StageResultState.SKIPPED,
            message="Rig is not applicable.",
        )
        motion = MotionImplementation()
        exporter = ExportImplementation()
        for implementation in (
            input_implementation,
            geometry,
            rig,
            motion,
            exporter,
        ):
            registry.register(implementation)
        plan = PipelinePlan(selections=(
            selection(PipelineStage.INPUT, "projection-images"),
            selection(PipelineStage.GEOMETRY, "native-hull"),
            selection(PipelineStage.RIG, "auto-rig"),
            selection(PipelineStage.MOTION, "canonical-motion"),
            selection(PipelineStage.EXPORT, "glb"),
        ))

        report = PipelineRunner(registry).run(plan, PipelineContext())

        self.assertTrue(report.success, report.failure_message)
        records = {record.selection.stage: record for record in report.records}
        self.assertTrue(records[PipelineStage.RIG].result.skipped)
        self.assertTrue(records[PipelineStage.MOTION].result.skipped)
        self.assertEqual(
            records[PipelineStage.MOTION].result.metadata["skipped_dependencies"],
            ("rig",),
        )
        self.assertEqual(motion.execute_calls, 0)
        self.assertEqual(report.context.require_output(PipelineStage.EXPORT), "export-data")

    def test_required_stage_cannot_skip(self) -> None:
        registry = PipelineRegistry()
        input_implementation = InputImplementation()
        geometry = FakeImplementation(
            identifier="native-hull",
            stage=PipelineStage.GEOMETRY,
            result_state=StageResultState.SKIPPED,
        )
        registry.register(input_implementation)
        registry.register(geometry)
        plan = PipelinePlan(selections=(
            selection(PipelineStage.INPUT, "projection-images"),
            selection(PipelineStage.GEOMETRY, "native-hull"),
        ))

        report = PipelineRunner(registry).run(plan, PipelineContext())

        self.assertFalse(report.success)
        self.assertTrue(report.records[-1].failed)
        self.assertIn("cannot be skipped", report.records[-1].result.message)


if __name__ == "__main__":
    unittest.main()
