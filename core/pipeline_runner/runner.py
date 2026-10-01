from __future__ import annotations

import time
from typing import Any

from ..pipeline_contracts import (
    PIPELINE_STAGE_ORDER, PIPELINE_STAGE_SPECS, ImplementationAvailability,
    PipelineContext, PipelinePlan, PipelineStage, PipelineStageSelection,
    StageExecutionResult, stage_spec,
)
from ..pipeline_registry import PipelineRegistry
from .models import PipelineExecutionReport, PipelineRunIssue, PipelineRunOptions, StageRunRecord
from .results import failed_result, result_for_exception, skipped_result


class PipelineRunner:
    def __init__(self, registry: PipelineRegistry) -> None:
        self.registry = registry

    def preflight(self, plan: PipelinePlan, context: PipelineContext) -> tuple[PipelineRunIssue, ...]:
        issues = [
            PipelineRunIssue(issue.stage, issue.message, issue.implementation_id)
            for issue in self.registry.validate_plan(plan, context, check_availability=False).issues
        ]
        for selection in plan.enabled_selections:
            for dependency in stage_spec(selection.stage).required_stages:
                if context.has_output(dependency):
                    continue
                dependency_selection = plan.selection_for(dependency)
                if dependency_selection is None or not dependency_selection.enabled:
                    state = (
                        "has no enabled implementation selected"
                        if dependency_selection is None
                        else "is disabled"
                    )
                    issues.append(PipelineRunIssue(
                        selection.stage,
                        (
                            f'Required pipeline dependency "{dependency.value}" '
                            f'{state} for stage "{selection.stage.value}".'
                        ),
                        selection.implementation_id,
                    ))
        for spec in PIPELINE_STAGE_SPECS:
            if spec.optional or context.has_output(spec.stage):
                continue
            selection = plan.selection_for(spec.stage)
            if selection is None:
                issues.append(PipelineRunIssue(spec.stage, "Required pipeline stage has no implementation selected."))
            elif not selection.enabled:
                issues.append(PipelineRunIssue(spec.stage, "Required pipeline stage is disabled.", selection.implementation_id))
        return tuple(issues)

    def _missing_dependencies(self, stage: PipelineStage, context: PipelineContext) -> tuple[PipelineStage, ...]:
        return tuple(dependency for dependency in stage_spec(stage).required_stages if not context.has_output(dependency))

    def _validate_result(self, selection: PipelineStageSelection, result: Any) -> StageExecutionResult:
        if not isinstance(result, StageExecutionResult):
            return failed_result(selection, "Implementation returned an invalid result. Expected StageExecutionResult.", metadata={"returned_type": type(result).__name__})
        if result.stage != selection.stage:
            return failed_result(selection, f'Implementation returned result for pipeline stage "{result.stage.value}" instead of "{selection.stage.value}".')
        if result.implementation_id != selection.implementation_id:
            return failed_result(selection, f'Implementation returned result with id "{result.implementation_id}" instead of "{selection.implementation_id}".')
        if result.skipped and not stage_spec(selection.stage).optional:
            return failed_result(
                selection,
                f'Required pipeline stage "{selection.stage.value}" cannot be skipped.',
            )
        return result

    def _record(self, selection: PipelineStageSelection, started: float, result: StageExecutionResult, availability: ImplementationAvailability | None = None) -> StageRunRecord:
        return StageRunRecord(selection, result, time.perf_counter() - started, availability)

    def _run_selection(self, selection: PipelineStageSelection, context: PipelineContext, options: PipelineRunOptions) -> StageRunRecord:
        started = time.perf_counter()
        if not selection.enabled:
            return self._record(selection, started, skipped_result(selection, "Stage disabled."))
        missing = self._missing_dependencies(selection.stage, context)
        if missing:
            names = ", ".join(dependency.value for dependency in missing)
            verb = "are" if len(missing) > 1 else "is"
            return self._record(selection, started, failed_result(
                selection, f"Required pipeline output{'s' if len(missing) > 1 else ''} {verb} missing: {names}.",
                metadata={"missing_dependencies": [dependency.value for dependency in missing]},
            ))
        try:
            implementation = self.registry.resolve_selection(selection)
        except Exception as exc:
            if not options.catch_exceptions:
                raise
            return self._record(selection, started, result_for_exception(selection, exc))
        availability = None
        if options.check_availability:
            try:
                availability = implementation.availability(context)
            except Exception as exc:
                if not options.catch_exceptions:
                    raise
                return self._record(selection, started, result_for_exception(selection, exc))
            if not isinstance(availability, ImplementationAvailability):
                return self._record(selection, started, failed_result(selection, "availability() returned an invalid result.", metadata={"returned_type": type(availability).__name__}))
            if not availability.available:
                message = availability.reason.strip() or "Implementation is unavailable."
                return self._record(selection, started, failed_result(selection, message, metadata={"availability_state": availability.state.value}), availability)
        try:
            raw_result = implementation.execute(context)
        except Exception as exc:
            if not options.catch_exceptions:
                raise
            result = result_for_exception(selection, exc)
        else:
            result = self._validate_result(selection, raw_result)
        if result.success and result.payload is not None:
            context.set_output(selection.stage, result.payload)
        return self._record(selection, started, result, availability)

    def run(self, plan: PipelinePlan, context: PipelineContext | None = None, *, options: PipelineRunOptions | None = None) -> PipelineExecutionReport:
        context, options = context or PipelineContext(), options or PipelineRunOptions()
        started = time.perf_counter()
        issues = list(self.preflight(plan, context))
        if issues:
            return PipelineExecutionReport(plan, context, (), tuple(issues), time.perf_counter() - started, True)
        records: list[StageRunRecord] = []
        aborted = False
        runtime_skipped_stages: set[PipelineStage] = set()
        for stage in PIPELINE_STAGE_ORDER:
            selection = plan.selection_for(stage)
            if selection is None:
                continue
            propagated_dependencies = tuple(
                dependency
                for dependency in stage_spec(stage).required_stages
                if dependency in runtime_skipped_stages
                and not context.has_output(dependency)
            )
            if selection.enabled and propagated_dependencies:
                names = ", ".join(
                    dependency.value for dependency in propagated_dependencies
                )
                started_stage = time.perf_counter()
                record = self._record(
                    selection,
                    started_stage,
                    skipped_result(
                        selection,
                        f'Stage skipped because optional dependency was skipped: {names}.',
                        metadata={
                            "skipped_dependencies": tuple(
                                dependency.value
                                for dependency in propagated_dependencies
                            )
                        },
                    ),
                )
            else:
                record = self._run_selection(selection, context, options)
            records.append(record)
            if record.result.skipped:
                runtime_skipped_stages.add(stage)
            if record.failed and options.stop_on_failure:
                aborted = True
                break
        return PipelineExecutionReport(plan, context, tuple(records), tuple(issues), time.perf_counter() - started, aborted)
