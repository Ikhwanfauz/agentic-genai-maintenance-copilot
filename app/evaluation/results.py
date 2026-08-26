from collections.abc import Sequence
from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)


class EvaluationMetric(StrEnum):
    TERMINAL_STATUS = "terminal_status"
    INVESTIGATION_OUTCOME = "investigation_outcome"
    GROUNDING_DECISION = "grounding_decision"
    EVIDENCE_COVERAGE = "evidence_coverage"
    CITATION_VALIDITY = "citation_validity"
    CITATION_COMPLETENESS = "citation_completeness"
    TOOL_SELECTION = "tool_selection"
    TOOL_ARGUMENTS = "tool_arguments"
    CLAIM_SUPPORT = "claim_support"
    FORBIDDEN_CLAIMS = "forbidden_claims"
    DIAGNOSIS_QUALITY = "diagnosis_quality"
    PROPOSAL_ELIGIBILITY = "proposal_eligibility"
    APPROVAL_BOUNDARY = "approval_boundary"
    TRAJECTORY_BOUNDS = "trajectory_bounds"
    PHYSICAL_EXECUTION_BOUNDARY = "physical_execution_boundary"


class EvaluationMetricStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class EvaluationMetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: EvaluationMetric
    status: EvaluationMetricStatus
    score: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=1000)
    expected: JsonValue | None = None
    actual: JsonValue | None = None
    details: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_metric_result(self) -> Self:
        if self.status == EvaluationMetricStatus.PASSED and self.score != 1.0:
            raise ValueError("A passed deterministic metric must have score 1.0.")

        if self.status == EvaluationMetricStatus.FAILED and self.score >= 1.0:
            raise ValueError("A failed deterministic metric must have score below 1.0.")

        if self.status == EvaluationMetricStatus.FAILED and not self.details:
            raise ValueError("A failed deterministic metric requires failure details.")

        return self


def create_binary_metric_result(
    metric: EvaluationMetric,
    matches: bool,
    *,
    summary: str,
    expected: JsonValue | None = None,
    actual: JsonValue | None = None,
    failure_details: Sequence[str] = (),
) -> EvaluationMetricResult:
    """Create one deterministic pass-or-fail metric result."""

    details = (
        []
        if matches
        else list(failure_details) or ["Actual result did not match the expected result."]
    )

    return EvaluationMetricResult(
        metric=metric,
        status=(EvaluationMetricStatus.PASSED if matches else EvaluationMetricStatus.FAILED),
        score=1.0 if matches else 0.0,
        summary=summary,
        expected=expected,
        actual=actual,
        details=details,
    )
