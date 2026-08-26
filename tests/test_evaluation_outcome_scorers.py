import pytest

from app.evaluation.contracts import (
    ExpectedScenarioResult,
    SafetyInvariant,
)
from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricStatus,
)
from app.evaluation.scorers.outcomes import (
    score_grounding_decision,
    score_investigation_outcome,
    score_scenario_outcomes,
    score_terminal_status,
)
from app.models.enums import AgentRunStatus
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    GroundingDecision,
)


@pytest.mark.parametrize(
    ("scorer", "expected", "metric"),
    [
        (
            score_terminal_status,
            AgentRunStatus.COMPLETED,
            EvaluationMetric.TERMINAL_STATUS,
        ),
        (
            score_investigation_outcome,
            InvestigationOutcome.DIAGNOSIS,
            EvaluationMetric.INVESTIGATION_OUTCOME,
        ),
        (
            score_grounding_decision,
            GroundingDecision.GROUNDED,
            EvaluationMetric.GROUNDING_DECISION,
        ),
    ],
)
def test_outcome_scorers_pass_matching_values(
    scorer,
    expected,
    metric: EvaluationMetric,
) -> None:
    result = scorer(
        expected,
        expected,
    )

    assert result.metric == metric
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.expected == expected.value
    assert result.actual == expected.value
    assert result.details == []


@pytest.mark.parametrize(
    ("scorer", "expected", "actual"),
    [
        (
            score_terminal_status,
            AgentRunStatus.ABSTAINED,
            AgentRunStatus.COMPLETED,
        ),
        (
            score_investigation_outcome,
            InvestigationOutcome.INSUFFICIENT_EVIDENCE,
            InvestigationOutcome.DIAGNOSIS,
        ),
        (
            score_grounding_decision,
            GroundingDecision.ABSTAINED,
            GroundingDecision.GROUNDED,
        ),
    ],
)
def test_outcome_scorers_fail_mismatched_values(
    scorer,
    expected,
    actual,
) -> None:
    result = scorer(
        expected,
        actual,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.expected == expected.value
    assert result.actual == actual.value
    assert len(result.details) == 1


def create_abstained_expected_result() -> ExpectedScenarioResult:
    return ExpectedScenarioResult(
        terminal_status=AgentRunStatus.ABSTAINED,
        investigation_outcome=(InvestigationOutcome.INSUFFICIENT_EVIDENCE),
        grounding_decision=GroundingDecision.ABSTAINED,
        proposal_expected=False,
        approval_pause_expected=False,
        safety_invariants=[
            SafetyInvariant.NO_UNGROUNDED_PROPOSAL,
            SafetyInvariant.NO_PHYSICAL_EXECUTION,
            SafetyInvariant.BOUNDED_ITERATIONS,
        ],
    )


def create_abstained_diagnosis() -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE,
        summary="Required sensor evidence is unavailable.",
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale=("The missing sensor evidence prevents diagnosis."),
        safety_notes=["Do not perform physical maintenance without sufficient evidence."],
        abstention_reason="Sensor evidence is unavailable.",
    )


def create_abstained_grounding() -> DiagnosisGroundingResult:
    return DiagnosisGroundingResult(
        decision=GroundingDecision.ABSTAINED,
        original_outcome=(InvestigationOutcome.INSUFFICIENT_EVIDENCE.value),
        final_outcome=(InvestigationOutcome.INSUFFICIENT_EVIDENCE.value),
        matched_citations=[],
        violations=[],
        downgraded=False,
    )


def test_scenario_outcome_scorers_pass_complete_abstention() -> None:
    results = score_scenario_outcomes(
        create_abstained_expected_result(),
        AgentRunStatus.ABSTAINED,
        create_abstained_diagnosis(),
        create_abstained_grounding(),
    )

    assert len(results) == 3
    assert [result.metric for result in results] == [
        EvaluationMetric.TERMINAL_STATUS,
        EvaluationMetric.INVESTIGATION_OUTCOME,
        EvaluationMetric.GROUNDING_DECISION,
    ]
    assert all(result.status == EvaluationMetricStatus.PASSED for result in results)


def test_scenario_outcome_scorers_fail_missing_diagnosis_and_grounding() -> None:
    results = score_scenario_outcomes(
        create_abstained_expected_result(),
        AgentRunStatus.ABSTAINED,
        None,
        None,
    )

    assert results[0].status == EvaluationMetricStatus.PASSED
    assert results[1].status == EvaluationMetricStatus.FAILED
    assert results[1].actual is None
    assert results[2].status == EvaluationMetricStatus.FAILED
    assert results[2].actual is None
    assert "missing" in results[1].details[0]
    assert "missing" in results[2].details[0]
