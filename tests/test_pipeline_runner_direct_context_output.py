from __future__ import annotations

from tests.pipeline_runner_test_support import *  # noqa: F403

class DirectContextOutputTests(unittest.TestCase):

    def test_implementation_can_store_output_directly(self) -> None:
        registry = PipelineRegistry()
        input_impl = DirectContextOutputImplementation(identifier='projection-images', stage=PipelineStage.INPUT)
        geometry = GeometryImplementation()
        registry.register(input_impl)
        registry.register(geometry)
        context = PipelineContext()
        report = PipelineRunner(registry).run(full_plan(material=False, rig=False, export=False), context)
        self.assertTrue(report.success)
        self.assertEqual(context.get_output(PipelineStage.INPUT), 'direct-output')
