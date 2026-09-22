from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class ExceptionTests(unittest.TestCase):

    def test_execution_exception_becomes_failed_result(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        implementation = ExplodingImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY)
        registry.register(implementation)
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        self.assertTrue(report.failed)
        record = report.record_for(PipelineStage.GEOMETRY)
        self.assertIn('execution exploded', record.result.message)
        self.assertEqual(record.result.metadata['exception_type'], 'RuntimeError')

    def test_execution_exception_can_escape(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        registry.register(ExplodingImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY))
        with self.assertRaises(RuntimeError):
            PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext(), options=PipelineRunOptions(catch_exceptions=False))

    def test_availability_exception_becomes_failure(self) -> None:
        registry = PipelineRegistry()
        registry.register(InputImplementation())
        implementation = ExplodingAvailabilityImplementation(identifier='native-hull', stage=PipelineStage.GEOMETRY)
        registry.register(implementation)
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), PipelineContext())
        self.assertTrue(report.failed)
        self.assertIn('availability exploded', report.record_for(PipelineStage.GEOMETRY).result.message)
