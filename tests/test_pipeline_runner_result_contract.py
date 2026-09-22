from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class ResultContractTests(unittest.TestCase):

    def test_invalid_result_type_becomes_failure(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        implementation = InvalidResultImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY)
        registry.register(implementation)
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        record = report.record_for(PipelineStage.GEOMETRY)
        self.assertTrue(record.failed)
        self.assertIn('StageExecutionResult', record.result.message)

    def test_wrong_stage_result_becomes_failure(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        registry.register(WrongStageResultImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY))
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        record = report.record_for(PipelineStage.GEOMETRY)
        self.assertTrue(record.failed)
        self.assertIn('instead of', record.result.message)

    def test_wrong_implementation_id_becomes_failure(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        registry.register(WrongIdResultImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY))
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        record = report.record_for(PipelineStage.GEOMETRY)
        self.assertTrue(record.failed)
        self.assertIn('another-implementation', record.result.message)

    def test_invalid_availability_type_becomes_failure(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        implementation = InvalidAvailabilityImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY)
        registry.register(implementation)
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        record = report.record_for(PipelineStage.GEOMETRY)
        self.assertTrue(record.failed)
        self.assertIn('availability', record.result.message)
