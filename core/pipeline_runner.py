from __future__ import annotations

import time

from dataclasses import dataclass
from typing import Any

from .pipeline_contracts import (
    AvailabilityState,
    ImplementationAvailability,
    PipelineContext,
    PipelinePlan,
    PipelineStage,
    PipelineStageSelection,
    StageExecutionResult,
    StageResultState,
    PIPELINE_STAGE_ORDER,
    PIPELINE_STAGE_SPECS,
    stage_spec,
)
from .pipeline_registry import (
    PipelineRegistry,
)


# ---------------------------------------------------------
# Errors
# ---------------------------------------------------------

class PipelineRunnerError(
    RuntimeError
):
    """
    Base runner error.
    """


class PipelineExecutionError(
    PipelineRunnerError
):
    """
    Raised when a completed pipeline report contains errors.
    """

    def __init__(
        self,
        report: "PipelineExecutionReport",
    ) -> None:
        self.report = report

        message = (
            report.failure_message
            or "Pipeline execution failed."
        )

        super().__init__(
            message
        )


# ---------------------------------------------------------
# Run issues
# ---------------------------------------------------------

@dataclass(frozen=True)
class PipelineRunIssue:
    """
    Structural problem detected before or during execution.

    Unlike StageExecutionResult, an issue does not
    necessarily belong to an implementation which actually
    ran.

    Examples:

        - missing required stage;
        - unknown implementation;
        - disabled required stage.
    """

    stage: PipelineStage | None

    message: str

    implementation_id: str | None = None


# ---------------------------------------------------------
# Stage record
# ---------------------------------------------------------

@dataclass(frozen=True)
class StageRunRecord:
    """
    Runtime record for one selected pipeline stage.
    """

    selection: PipelineStageSelection

    result: StageExecutionResult

    duration_seconds: float

    availability: (
        ImplementationAvailability
        | None
    ) = None

    @property
    def stage(
        self,
    ) -> PipelineStage:
        return (
            self.selection.stage
        )

    @property
    def implementation_id(
        self,
    ) -> str:
        return (
            self.selection
            .implementation_id
        )

    @property
    def success(
        self,
    ) -> bool:
        return (
            self.result.success
        )

    @property
    def failed(
        self,
    ) -> bool:
        return (
            self.result.failed
        )

    @property
    def skipped(
        self,
    ) -> bool:
        return (
            self.result.skipped
        )


# ---------------------------------------------------------
# Pipeline execution report
# ---------------------------------------------------------

@dataclass(frozen=True)
class PipelineExecutionReport:
    """
    Complete result of one PipelineRunner.run() call.
    """

    plan: PipelinePlan

    context: PipelineContext

    records: tuple[
        StageRunRecord,
        ...
    ]

    issues: tuple[
        PipelineRunIssue,
        ...
    ]

    duration_seconds: float

    aborted: bool

    @property
    def failed_records(
        self,
    ) -> tuple[
        StageRunRecord,
        ...
    ]:
        return tuple(
            record
            for record
            in self.records
            if record.failed
        )

    @property
    def successful_records(
        self,
    ) -> tuple[
        StageRunRecord,
        ...
    ]:
        return tuple(
            record
            for record
            in self.records
            if record.success
        )

    @property
    def skipped_records(
        self,
    ) -> tuple[
        StageRunRecord,
        ...
    ]:
        return tuple(
            record
            for record
            in self.records
            if record.skipped
        )

    @property
    def success(
        self,
    ) -> bool:
        return (
            not self.issues
            and not self.failed_records
            and not self.aborted
        )

    @property
    def failed(
        self,
    ) -> bool:
        return not self.success

    @property
    def failure_message(
        self,
    ) -> str:
        messages: list[str] = []

        for issue in self.issues:
            prefix = ""

            if issue.stage is not None:
                prefix = (
                    f"{issue.stage.value}: "
                )

            if issue.implementation_id:
                prefix += (
                    f"{issue.implementation_id}: "
                )

            messages.append(
                prefix
                + issue.message
            )

        for record in self.failed_records:
            message = (
                record.result.message.strip()
                or "Stage failed."
            )

            messages.append(
                (
                    f"{record.stage.value}: "
                    f"{record.implementation_id}: "
                    f"{message}"
                )
            )

        return "\n".join(
            messages
        )

    def record_for(
        self,
        stage: PipelineStage,
    ) -> (
        StageRunRecord
        | None
    ):
        normalized_stage = (
            PipelineStage(stage)
        )

        for record in self.records:
            if (
                record.stage
                == normalized_stage
            ):
                return record

        return None

    def result_for(
        self,
        stage: PipelineStage,
    ) -> (
        StageExecutionResult
        | None
    ):
        record = self.record_for(
            stage
        )

        if record is None:
            return None

        return (
            record.result
        )

    def raise_for_failure(
        self,
    ) -> None:
        if self.success:
            return

        raise PipelineExecutionError(
            self
        )


# ---------------------------------------------------------
# Execution options
# ---------------------------------------------------------

@dataclass(frozen=True)
class PipelineRunOptions:
    """
    Controls runner failure behaviour.

    stop_on_failure:
        Stop executing subsequent stages when one stage
        fails.

    catch_exceptions:
        Convert implementation exceptions to FAILED results.

        This should normally remain True for the Blender UI
        so users receive a clean product-level failure.

        Tests and development tools may disable it to expose
        raw exceptions directly.

    check_availability:
        Call implementation.availability(context) immediately
        before execution.

        Availability is intentionally checked dynamically,
        not globally during preflight, because later stages
        may depend on outputs created by earlier stages.
    """

    stop_on_failure: bool = True

    catch_exceptions: bool = True

    check_availability: bool = True


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _result_for_exception(
    selection: PipelineStageSelection,
    exc: Exception,
) -> StageExecutionResult:
    return (
        StageExecutionResult
        .failed_result(
            stage=(
                selection.stage
            ),
            implementation_id=(
                selection
                .implementation_id
            ),
            message=str(
                exc
            )
            or (
                exc
                .__class__
                .__name__
            ),
            metadata={
                "exception_type": (
                    exc
                    .__class__
                    .__name__
                ),
            },
        )
    )


def _failed_result(
    selection: PipelineStageSelection,
    message: str,
    *,
    metadata: dict[
        str,
        Any,
    ]
    | None = None,
) -> StageExecutionResult:
    return (
        StageExecutionResult
        .failed_result(
            stage=(
                selection.stage
            ),
            implementation_id=(
                selection
                .implementation_id
            ),
            message=(
                message
            ),
            metadata=(
                metadata
                or {}
            ),
        )
    )


def _skipped_result(
    selection: PipelineStageSelection,
    message: str,
) -> StageExecutionResult:
    return (
        StageExecutionResult
        .skipped_result(
            stage=(
                selection.stage
            ),
            implementation_id=(
                selection
                .implementation_id
            ),
            message=(
                message
            ),
        )
    )


# ---------------------------------------------------------
# Runner
# ---------------------------------------------------------

class PipelineRunner:
    """
    Execute a Meshvenn PipelinePlan.

    The runner is intentionally implementation-agnostic.

    Concrete pipeline engines only need to implement:

        descriptor
        availability(context)
        execute(context)

    ---------------------------------------------------------
    Execution model
    ---------------------------------------------------------

        structural preflight

            ↓

        INPUT

            ↓

        GEOMETRY

            ↓
        ┌───────────────┐
        ↓               ↓
      MATERIAL          RIG

        └───────┬───────┘
                ↓

              EXPORT

    Actual order remains PIPELINE_STAGE_ORDER.

    ---------------------------------------------------------
    Outputs
    ---------------------------------------------------------

    When a successful implementation returns a non-None
    payload, that payload automatically becomes the output
    of its stage:

        context.set_output(
            stage,
            result.payload,
        )

    Implementations may alternatively populate context
    directly when they need more complex behaviour.
    """

    def __init__(
        self,
        registry: PipelineRegistry,
    ) -> None:
        self.registry = registry

    # -----------------------------------------------------
    # Preflight
    # -----------------------------------------------------

    def preflight(
        self,
        plan: PipelinePlan,
        context: PipelineContext,
    ) -> tuple[
        PipelineRunIssue,
        ...
    ]:
        """
        Validate structural pipeline configuration.

        Availability is deliberately NOT checked here.

        Example:

            AutoRig.availability()

        may require the geometry object produced only after
        the GEOMETRY stage has executed.
        """

        issues: list[
            PipelineRunIssue
        ] = []

        # -------------------------------------------------
        # Registry / stage validation
        # -------------------------------------------------

        registry_validation = (
            self.registry
            .validate_plan(
                plan,
                context,
                check_availability=False,
            )
        )

        for issue in (
            registry_validation
            .issues
        ):
            issues.append(
                PipelineRunIssue(
                    stage=(
                        issue.stage
                    ),
                    implementation_id=(
                        issue
                        .implementation_id
                    ),
                    message=(
                        issue.message
                    ),
                )
            )

        # -------------------------------------------------
        # Required high-level stages
        #
        # A required stage can be omitted if its output is
        # already present in PipelineContext.
        #
        # This will later allow workflows such as:
        #
        #     existing Blender mesh
        #         ↓
        #     MATERIAL
        #         ↓
        #     RIG
        #
        # without rebuilding geometry.
        # -------------------------------------------------

        for spec in (
            PIPELINE_STAGE_SPECS
        ):
            if spec.optional:
                continue

            if context.has_output(
                spec.stage
            ):
                continue

            selection = (
                plan.selection_for(
                    spec.stage
                )
            )

            if selection is None:
                issues.append(
                    PipelineRunIssue(
                        stage=(
                            spec.stage
                        ),
                        implementation_id=None,
                        message=(
                            "Required pipeline stage "
                            "has no implementation selected."
                        ),
                    )
                )

                continue

            if not selection.enabled:
                issues.append(
                    PipelineRunIssue(
                        stage=(
                            spec.stage
                        ),
                        implementation_id=(
                            selection
                            .implementation_id
                        ),
                        message=(
                            "Required pipeline stage "
                            "is disabled."
                        ),
                    )
                )

        return tuple(
            issues
        )

    # -----------------------------------------------------
    # Dependencies
    # -----------------------------------------------------

    def _missing_dependencies(
        self,
        stage: PipelineStage,
        context: PipelineContext,
    ) -> tuple[
        PipelineStage,
        ...
    ]:
        spec = stage_spec(
            stage
        )

        return tuple(
            dependency
            for dependency
            in spec.required_stages
            if not context.has_output(
                dependency
            )
        )

    # -----------------------------------------------------
    # Result validation
    # -----------------------------------------------------

    def _validate_result(
        self,
        selection: PipelineStageSelection,
        result: Any,
    ) -> StageExecutionResult:
        """
        Ensure implementations cannot accidentally return a
        result for another stage/id.
        """

        if not isinstance(
            result,
            StageExecutionResult,
        ):
            return _failed_result(
                selection,
                (
                    "Implementation returned an invalid "
                    "result. Expected StageExecutionResult."
                ),
                metadata={
                    "returned_type": (
                        type(
                            result
                        ).__name__
                    ),
                },
            )

        if (
            result.stage
            != selection.stage
        ):
            return _failed_result(
                selection,
                (
                    "Implementation returned result for "
                    f'pipeline stage "{result.stage.value}" '
                    "instead of "
                    f'"{selection.stage.value}".'
                ),
            )

        if (
            result.implementation_id
            != selection.implementation_id
        ):
            return _failed_result(
                selection,
                (
                    "Implementation returned result with "
                    f'id "{result.implementation_id}" '
                    "instead of "
                    f'"{selection.implementation_id}".'
                ),
            )

        return result

    # -----------------------------------------------------
    # Single stage
    # -----------------------------------------------------

    def _run_selection(
        self,
        selection: PipelineStageSelection,
        context: PipelineContext,
        options: PipelineRunOptions,
    ) -> StageRunRecord:
        started = (
            time.perf_counter()
        )

        # -------------------------------------------------
        # Disabled optional selection
        # -------------------------------------------------

        if not selection.enabled:
            result = (
                _skipped_result(
                    selection,
                    "Stage disabled.",
                )
            )

            return StageRunRecord(
                selection=(
                    selection
                ),
                result=result,
                duration_seconds=(
                    time.perf_counter()
                    - started
                ),
                availability=None,
            )

        # -------------------------------------------------
        # Dependency outputs
        # -------------------------------------------------

        missing_dependencies = (
            self._missing_dependencies(
                selection.stage,
                context,
            )
        )

        if missing_dependencies:
            names = ", ".join(
                dependency.value
                for dependency
                in missing_dependencies
            )

            result = (
                _failed_result(
                    selection,
                    (
                        "Required pipeline output"
                        + (
                            "s are"
                            if len(
                                missing_dependencies
                            ) > 1
                            else " is"
                        )
                        + " missing: "
                        + names
                        + "."
                    ),
                    metadata={
                        "missing_dependencies": [
                            dependency.value
                            for dependency
                            in missing_dependencies
                        ]
                    },
                )
            )

            return StageRunRecord(
                selection=(
                    selection
                ),
                result=result,
                duration_seconds=(
                    time.perf_counter()
                    - started
                ),
                availability=None,
            )

        # -------------------------------------------------
        # Resolve implementation
        # -------------------------------------------------

        try:
            implementation = (
                self.registry
                .resolve_selection(
                    selection
                )
            )

        except Exception as exc:
            if not options.catch_exceptions:
                raise

            result = (
                _result_for_exception(
                    selection,
                    exc,
                )
            )

            return StageRunRecord(
                selection=(
                    selection
                ),
                result=result,
                duration_seconds=(
                    time.perf_counter()
                    - started
                ),
                availability=None,
            )

        # -------------------------------------------------
        # Dynamic availability
        # -------------------------------------------------

        availability: (
            ImplementationAvailability
            | None
        ) = None

        if options.check_availability:
            try:
                availability = (
                    implementation
                    .availability(
                        context
                    )
                )

            except Exception as exc:
                if not options.catch_exceptions:
                    raise

                result = (
                    _result_for_exception(
                        selection,
                        exc,
                    )
                )

                return StageRunRecord(
                    selection=(
                        selection
                    ),
                    result=result,
                    duration_seconds=(
                        time.perf_counter()
                        - started
                    ),
                    availability=None,
                )

            if not isinstance(
                availability,
                ImplementationAvailability,
            ):
                result = (
                    _failed_result(
                        selection,
                        (
                            "availability() returned an "
                            "invalid result."
                        ),
                        metadata={
                            "returned_type": (
                                type(
                                    availability
                                ).__name__
                            ),
                        },
                    )
                )

                return StageRunRecord(
                    selection=(
                        selection
                    ),
                    result=result,
                    duration_seconds=(
                        time.perf_counter()
                        - started
                    ),
                    availability=None,
                )

            if not availability.available:
                message = (
                    availability
                    .reason
                    .strip()
                    or (
                        "Implementation is "
                        "unavailable."
                    )
                )

                result = (
                    _failed_result(
                        selection,
                        message,
                        metadata={
                            "availability_state": (
                                availability
                                .state
                                .value
                            ),
                        },
                    )
                )

                return StageRunRecord(
                    selection=(
                        selection
                    ),
                    result=result,
                    duration_seconds=(
                        time.perf_counter()
                        - started
                    ),
                    availability=(
                        availability
                    ),
                )

        # -------------------------------------------------
        # Execute implementation
        # -------------------------------------------------

        try:
            raw_result = (
                implementation
                .execute(
                    context
                )
            )

        except Exception as exc:
            if not options.catch_exceptions:
                raise

            result = (
                _result_for_exception(
                    selection,
                    exc,
                )
            )

        else:
            result = (
                self._validate_result(
                    selection,
                    raw_result,
                )
            )

        # -------------------------------------------------
        # Successful payload becomes stage output.
        # -------------------------------------------------

        if (
            result.success
            and result.payload
            is not None
        ):
            context.set_output(
                selection.stage,
                result.payload,
            )

        return StageRunRecord(
            selection=(
                selection
            ),
            result=result,
            duration_seconds=(
                time.perf_counter()
                - started
            ),
            availability=(
                availability
            ),
        )

    # -----------------------------------------------------
    # Run
    # -----------------------------------------------------

    def run(
        self,
        plan: PipelinePlan,
        context: (
            PipelineContext
            | None
        ) = None,
        *,
        options: (
            PipelineRunOptions
            | None
        ) = None,
    ) -> PipelineExecutionReport:
        """
        Execute an entire PipelinePlan.

        PipelineContext is mutated in place so stage outputs
        become immediately available to subsequent stages.
        """

        if context is None:
            context = (
                PipelineContext()
            )

        if options is None:
            options = (
                PipelineRunOptions()
            )

        started = (
            time.perf_counter()
        )

        # -------------------------------------------------
        # Structural preflight
        # -------------------------------------------------

        issues = list(
            self.preflight(
                plan,
                context,
            )
        )

        if issues:
            return (
                PipelineExecutionReport(
                    plan=plan,
                    context=context,
                    records=(),
                    issues=tuple(
                        issues
                    ),
                    duration_seconds=(
                        time.perf_counter()
                        - started
                    ),
                    aborted=True,
                )
            )

        records: list[
            StageRunRecord
        ] = []

        aborted = False

        # -------------------------------------------------
        # Stable stage execution order
        # -------------------------------------------------

        for stage in (
            PIPELINE_STAGE_ORDER
        ):
            selection = (
                plan.selection_for(
                    stage
                )
            )

            # ---------------------------------------------
            # Stage not part of this plan.
            #
            # Optional stages may simply be absent.
            #
            # Required absent stages were already handled by
            # preflight unless context contained their output.
            # ---------------------------------------------

            if selection is None:
                continue

            record = (
                self._run_selection(
                    selection,
                    context,
                    options,
                )
            )

            records.append(
                record
            )

            if (
                record.failed
                and options.stop_on_failure
            ):
                aborted = True
                break

        return (
            PipelineExecutionReport(
                plan=plan,
                context=context,
                records=tuple(
                    records
                ),
                issues=tuple(
                    issues
                ),
                duration_seconds=(
                    time.perf_counter()
                    - started
                ),
                aborted=(
                    aborted
                ),
            )
        )


# ---------------------------------------------------------
# Convenience facade
# ---------------------------------------------------------

def run_pipeline(
    registry: PipelineRegistry,
    plan: PipelinePlan,
    context: (
        PipelineContext
        | None
    ) = None,
    *,
    options: (
        PipelineRunOptions
        | None
    ) = None,
) -> PipelineExecutionReport:
    """
    Convenience wrapper for callers which do not need to
    keep a PipelineRunner instance.
    """

    runner = (
        PipelineRunner(
            registry
        )
    )

    return runner.run(
        plan,
        context,
        options=options,
    )