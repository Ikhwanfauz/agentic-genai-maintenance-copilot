from app.evaluation.contracts import ExpectedScenarioResult
from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricResult,
    create_binary_metric_result,
)
from app.models.enums import AgentRunStatus
from app.schemas.diagnosis import (
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    GroundingDecision,
)


def _normalize_value(value: object) -> str | None:
    if value is None:
        return None

    enum_value = getattr(
        value,
        "value",
        value,
    )

    return str(enum_value)


def _score_expected_value(
    metric: EvaluationMetric,
    label: str,
    expected: object,
    actual: object,
) -> EvaluationMetricResult:
    expected_value = _normalize_value(expected)
    actual_value = _normalize_value(actual)
    matches = actual_value == expected_value
    displayed_actual = actual_value if actual_value is not None else "missing"

    return create_binary_metric_result(
        metric,
        matches,
        summary=(
            f"{label} matched the expected value."
            if matches
            else f"{label} did not match the expected value."
        ),
        expected=expected_value,
        actual=actual_value,
        failure_details=[
            (f"Expected {label.lower()} '{expected_value}' but received '{displayed_actual}'.")
        ],
    )


def score_terminal_status(
    expected: AgentRunStatus,
    actual: AgentRunStatus | str | None,
) -> EvaluationMetricResult:
    return _score_expected_value(
        EvaluationMetric.TERMINAL_STATUS,
        "Terminal status",
        expected,
        actual,
    )


def score_investigation_outcome(
    expected: InvestigationOutcome,
    actual: InvestigationOutcome | str | None,
) -> EvaluationMetricResult:
    return _score_expected_value(
        EvaluationMetric.INVESTIGATION_OUTCOME,
        "Investigation outcome",
        expected,
        actual,
    )


def score_grounding_decision(
    expected: GroundingDecision,
    actual: GroundingDecision | str | None,
) -> EvaluationMetricResult:
    return _score_expected_value(
        EvaluationMetric.GROUNDING_DECISION,
        "Grounding decision",
        expected,
        actual,
    )


def score_scenario_outcomes(
    expected: ExpectedScenarioResult,
    actual_status: AgentRunStatus | str | None,
    actual_diagnosis: MaintenanceDiagnosis | None,
    actual_grounding: DiagnosisGroundingResult | None,
) -> list[EvaluationMetricResult]:
    actual_outcome = actual_diagnosis.outcome if actual_diagnosis is not None else None
    actual_grounding_decision = actual_grounding.decision if actual_grounding is not None else None

    return [
        score_terminal_status(
            expected.terminal_status,
            actual_status,
        ),
        score_investigation_outcome(
            expected.investigation_outcome,
            actual_outcome,
        ),
        score_grounding_decision(
            expected.grounding_decision,
            actual_grounding_decision,
        ),
    ]
