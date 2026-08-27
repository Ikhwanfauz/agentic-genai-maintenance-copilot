from app.evaluation.contracts import EvaluationScenario
from app.evaluation.execution import (
    EvaluationResultStatus,
    EvaluationScenarioObservation,
    EvaluationScenarioResult,
)
from app.evaluation.results import EvaluationMetricStatus
from app.evaluation.scorers.claims import (
    score_claim_support,
    score_diagnosis_quality,
    score_forbidden_claims,
)
from app.evaluation.scorers.evidence import (
    score_citation_completeness,
    score_citation_validity,
    score_evidence_coverage,
)
from app.evaluation.scorers.outcomes import (
    score_scenario_outcomes,
)
from app.evaluation.scorers.safety import (
    score_approval_boundary,
    score_physical_execution_boundary,
    score_proposal_eligibility,
    score_trajectory_bounds,
)
from app.evaluation.scorers.tools import (
    score_tool_arguments,
    score_tool_selection,
)


def score_scenario_observation(
    scenario: EvaluationScenario,
    observation: EvaluationScenarioObservation,
) -> EvaluationScenarioResult:
    """Apply every deterministic metric to one observation."""

    if scenario.scenario_id != observation.scenario_id:
        raise ValueError("Evaluation scenario identity must match its execution observation.")

    expected = scenario.expected
    diagnosis = observation.run.diagnosis
    grounding = observation.grounding_result
    proposal = observation.run.work_order_proposal

    metric_results = [
        *score_scenario_outcomes(
            expected,
            observation.run.status,
            diagnosis,
            grounding,
        ),
        score_evidence_coverage(
            expected.required_evidence_sources,
            observation.evidence_ledger,
            scenario.request.asset_code,
        ),
        score_citation_validity(
            diagnosis,
            observation.evidence_ledger,
            scenario.request.asset_code,
        ),
        score_citation_completeness(
            expected.required_citations,
            diagnosis,
        ),
        score_tool_selection(
            expected.required_tools,
            expected.forbidden_tools,
            observation.tool_calls,
        ),
        score_tool_arguments(
            expected.required_tools,
            observation.tool_calls,
        ),
        score_claim_support(
            expected.required_claims,
            diagnosis,
        ),
        score_forbidden_claims(
            expected.forbidden_claim_concepts,
            diagnosis,
        ),
        score_diagnosis_quality(
            expected.required_claims,
            diagnosis,
        ),
        score_proposal_eligibility(
            expected.proposal_expected,
            diagnosis,
            grounding,
            proposal,
        ),
        score_approval_boundary(
            expected.approval_pause_expected,
            observation.run.status,
            proposal,
            observation.run.approval_interrupt,
            observation.run.approval_decision,
        ),
        score_trajectory_bounds(
            observation.iteration_count,
            observation.max_iterations,
            observation.visited_nodes,
        ),
        score_physical_execution_boundary(
            observation.tool_calls,
        ),
    ]

    status = (
        EvaluationResultStatus.PASSED
        if all(result.status == EvaluationMetricStatus.PASSED for result in metric_results)
        else EvaluationResultStatus.FAILED
    )

    return EvaluationScenarioResult(
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        fixture_id=scenario.fixture_id,
        status=status,
        metric_results=metric_results,
    )
