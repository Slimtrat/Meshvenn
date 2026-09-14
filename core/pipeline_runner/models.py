from __future__ import annotations

from dataclasses import dataclass

from ..pipeline_contracts import ImplementationAvailability, PipelineContext, PipelinePlan, PipelineStage, PipelineStageSelection, StageExecutionResult


class PipelineRunnerError(RuntimeError):
    pass


class PipelineExecutionError(PipelineRunnerError):
    def __init__(self, report: "PipelineExecutionReport") -> None:
        self.report = report
        super().__init__(report.failure_message or "Pipeline execution failed.")


@dataclass(frozen=True)
class PipelineRunIssue:
    stage: PipelineStage | None
    message: str
    implementation_id: str | None = None


@dataclass(frozen=True)
class StageRunRecord:
    selection: PipelineStageSelection
    result: StageExecutionResult
    duration_seconds: float
    availability: ImplementationAvailability | None = None

    @property
    def stage(self) -> PipelineStage:
        return self.selection.stage

    @property
    def implementation_id(self) -> str:
        return self.selection.implementation_id

    @property
    def success(self) -> bool:
        return self.result.success

    @property
    def failed(self) -> bool:
        return self.result.failed

    @property
    def skipped(self) -> bool:
        return self.result.skipped


@dataclass(frozen=True)
class PipelineExecutionReport:
    plan: PipelinePlan
    context: PipelineContext
    records: tuple[StageRunRecord, ...]
    issues: tuple[PipelineRunIssue, ...]
    duration_seconds: float
    aborted: bool

    @property
    def failed_records(self) -> tuple[StageRunRecord, ...]:
        return tuple(record for record in self.records if record.failed)

    @property
    def successful_records(self) -> tuple[StageRunRecord, ...]:
        return tuple(record for record in self.records if record.success)

    @property
    def skipped_records(self) -> tuple[StageRunRecord, ...]:
        return tuple(record for record in self.records if record.skipped)

    @property
    def success(self) -> bool:
        return not self.issues and not self.failed_records and not self.aborted

    @property
    def failed(self) -> bool:
        return not self.success

    @property
    def failure_message(self) -> str:
        messages = []
        for issue in self.issues:
            prefix = f"{issue.stage.value}: " if issue.stage is not None else ""
            if issue.implementation_id:
                prefix += f"{issue.implementation_id}: "
            messages.append(prefix + issue.message)
        for record in self.failed_records:
            message = record.result.message.strip() or "Stage failed."
            messages.append(f"{record.stage.value}: {record.implementation_id}: {message}")
        return "\n".join(messages)

    def record_for(self, stage: PipelineStage) -> StageRunRecord | None:
        stage = PipelineStage(stage)
        return next((record for record in self.records if record.stage == stage), None)

    def result_for(self, stage: PipelineStage) -> StageExecutionResult | None:
        record = self.record_for(stage)
        return None if record is None else record.result

    def raise_for_failure(self) -> None:
        if not self.success:
            raise PipelineExecutionError(self)


@dataclass(frozen=True)
class PipelineRunOptions:
    stop_on_failure: bool = True
    catch_exceptions: bool = True
    check_availability: bool = True
