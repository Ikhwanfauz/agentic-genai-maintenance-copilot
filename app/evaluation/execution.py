from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricResult,
    EvaluationMetricStatus,
)
from app.schemas.agent_api import AgentRunResponse
from app.schemas.evidence import CollectedEvidence
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    EvidenceCoverage,
)
from app.schemas.observability import ToolCallRecordInput


class EvaluationExecutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvaluationScenarioObservation(EvaluationExecutionModel):
    """Typed actual output collected from one scenario execution."""

    scenario_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^v7\.[a-z0-9][a-z0-9._-]*$",
    )
    run: AgentRunResponse
    grounding_result: DiagnosisGroundingResult | None = None
    evidence_coverage: EvidenceCoverage | None = None
    evidence_ledger: list[CollectedEvidence] = Field(
        default_factory=list,
        max_length=100,
    )
    tool_calls: list[ToolCallRecordInput] = Field(
        default_factory=list,
        max_length=100,
    )
    iteration_count: int
    max_iterations: int
    visited_nodes: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_observation_identity(self) -> Self:
        mismatched_run_ids = sorted(
            {
                tool_call.run_id
                for tool_call in self.tool_calls
                if tool_call.run_id != self.run.run_id
            }
        )

        if mismatched_run_ids:
            raise ValueError("Observed tool-call run IDs must match the agent-run identity.")

        return self


class EvaluationResultStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class EvaluationScenarioResult(EvaluationExecutionModel):
    """Machine-readable result for one evaluated scenario."""

    result_version: Literal[1] = 1
    scenario_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^v7\.[a-z0-9][a-z0-9._-]*$",
    )
    scenario_version: int = Field(gt=0)
    fixture_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    status: EvaluationResultStatus
    metric_results: list[EvaluationMetricResult] = Field(
        default_factory=list,
        max_length=len(EvaluationMetric),
    )
    error_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )
    error_message: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
    )

    @model_validator(mode="after")
    def validate_scenario_result(self) -> Self:
        if self.status == EvaluationResultStatus.ERROR:
            if self.metric_results:
                raise ValueError("An execution-error result must not contain metric results.")

            if self.error_type is None or self.error_message is None:
                raise ValueError("An execution-error result requires error details.")

            return self

        if self.error_type is not None or self.error_message is not None:
            raise ValueError("A scored scenario result must not contain execution-error details.")

        observed_metrics = [result.metric for result in self.metric_results]
        expected_metrics = list(EvaluationMetric)

        if observed_metrics != expected_metrics:
            raise ValueError(
                "A scored scenario result must contain every "
                "evaluation metric exactly once in declared order."
            )

        has_failed_metric = any(
            result.status == EvaluationMetricStatus.FAILED for result in self.metric_results
        )

        if self.status == EvaluationResultStatus.PASSED and has_failed_metric:
            raise ValueError("A passed scenario must not contain failed metrics.")

        if self.status == EvaluationResultStatus.FAILED and not has_failed_metric:
            raise ValueError("A failed scenario requires at least one failed metric.")

        return self


class EvaluationDatasetResult(EvaluationExecutionModel):
    """Machine-readable aggregate for one dataset execution."""

    result_version: Literal[1] = 1
    dataset_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^v7\.[a-z0-9][a-z0-9._-]*$",
    )
    dataset_version: int = Field(gt=0)
    status: EvaluationResultStatus
    scenario_results: list[EvaluationScenarioResult] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_dataset_result(self) -> Self:
        scenario_ids = [result.scenario_id for result in self.scenario_results]

        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Evaluation dataset results must have unique scenario IDs.")

        scenario_statuses = {result.status for result in self.scenario_results}

        if EvaluationResultStatus.ERROR in scenario_statuses:
            expected_status = EvaluationResultStatus.ERROR
        elif EvaluationResultStatus.FAILED in scenario_statuses:
            expected_status = EvaluationResultStatus.FAILED
        else:
            expected_status = EvaluationResultStatus.PASSED

        if self.status != expected_status:
            raise ValueError("Dataset result status must match its scenario result statuses.")

        return self
