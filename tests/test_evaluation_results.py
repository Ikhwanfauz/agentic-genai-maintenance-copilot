import pytest
from pydantic import ValidationError

from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricResult,
    EvaluationMetricStatus,
    create_binary_metric_result,
)


def test_metric_result_accepts_deterministic_pass() -> None:
    result = EvaluationMetricResult(
        metric=EvaluationMetric.TERMINAL_STATUS,
        status=EvaluationMetricStatus.PASSED,
        score=1.0,
        summary="Terminal status matched.",
        expected="completed",
        actual="completed",
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.details == []


def test_metric_result_accepts_deterministic_failure() -> None:
    result = EvaluationMetricResult(
        metric=EvaluationMetric.TERMINAL_STATUS,
        status=EvaluationMetricStatus.FAILED,
        score=0.0,
        summary="Terminal status did not match.",
        expected="abstained",
        actual="completed",
        details=[
            "Expected abstained but received completed.",
        ],
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert len(result.details) == 1


def test_passed_metric_requires_full_score() -> None:
    with pytest.raises(
        ValidationError,
        match="passed deterministic metric must have score 1.0",
    ):
        EvaluationMetricResult(
            metric=EvaluationMetric.CITATION_VALIDITY,
            status=EvaluationMetricStatus.PASSED,
            score=0.5,
            summary="Invalid passed result.",
        )


def test_failed_metric_requires_score_below_one() -> None:
    with pytest.raises(
        ValidationError,
        match="failed deterministic metric must have score below 1.0",
    ):
        EvaluationMetricResult(
            metric=EvaluationMetric.CITATION_VALIDITY,
            status=EvaluationMetricStatus.FAILED,
            score=1.0,
            summary="Invalid failed result.",
            details=[
                "A failure cannot receive the full deterministic score.",
            ],
        )


def test_failed_metric_requires_failure_details() -> None:
    with pytest.raises(
        ValidationError,
        match="requires failure details",
    ):
        EvaluationMetricResult(
            metric=EvaluationMetric.TOOL_SELECTION,
            status=EvaluationMetricStatus.FAILED,
            score=0.0,
            summary="Tool selection failed.",
        )


def test_binary_helper_creates_passing_result() -> None:
    result = create_binary_metric_result(
        EvaluationMetric.GROUNDING_DECISION,
        True,
        summary="Grounding decision matched.",
        expected="grounded",
        actual="grounded",
        failure_details=[
            "This detail must not be included for a passing metric.",
        ],
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.details == []


def test_binary_helper_creates_failure_with_default_detail() -> None:
    result = create_binary_metric_result(
        EvaluationMetric.INVESTIGATION_OUTCOME,
        False,
        summary="Investigation outcome did not match.",
        expected="insufficient_evidence",
        actual="diagnosis",
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.details == ["Actual result did not match the expected result."]
