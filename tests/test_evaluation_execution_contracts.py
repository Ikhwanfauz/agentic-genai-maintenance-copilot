from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.evaluation.execution import (
    EvaluationDatasetResult,
    EvaluationResultStatus,
    EvaluationScenarioObservation,
    EvaluationScenarioResult,
)
from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricResult,
    create_binary_metric_result,
)
from app.models.enums import (
    AgentRunStatus,
    ToolCallStatus,
)
from app.schemas.agent_api import AgentRunResponse
from app.schemas.diagnosis import EvidenceSourceType
from app.schemas.evidence import CollectedEvidence
from app.schemas.observability import ToolCallRecordInput

OBSERVED_AT = datetime(
    2026,
    8,
    27,
    12,
    0,
    tzinfo=UTC,
)


def create_run_response(
    *,
    run_id: str = "evaluation-run",
) -> AgentRunResponse:
    return AgentRunResponse(
        run_id=run_id,
        thread_id="evaluation-thread",
        status=AgentRunStatus.COMPLETED,
        started_at=OBSERVED_AT,
        completed_at=OBSERVED_AT,
        final_response="Evaluation fixture completed.",
    )


def create_tool_call(
    *,
    run_id: str = "evaluation-run",
) -> ToolCallRecordInput:
    return ToolCallRecordInput(
        run_id=run_id,
        tool_name="get_asset_details",
        arguments_json={"asset_code": "P-101"},
        result_json={"asset_code": "P-101"},
        status=ToolCallStatus.SUCCEEDED,
        started_at=OBSERVED_AT,
        completed_at=OBSERVED_AT,
        latency_ms=0,
    )


def create_evidence() -> CollectedEvidence:
    return CollectedEvidence(
        tool_call_id="evaluation-tool-call",
        tool_name="get_asset_details",
        source_type=EvidenceSourceType.ASSET_DETAILS,
        source_id="P-101",
        citation="asset:P-101",
        asset_code="P-101",
        payload={"asset_code": "P-101"},
    )


def create_observation() -> EvaluationScenarioObservation:
    return EvaluationScenarioObservation(
        scenario_id="v7.normal.test-observation",
        run=create_run_response(),
        evidence_ledger=[create_evidence()],
        tool_calls=[create_tool_call()],
        iteration_count=1,
        max_iterations=6,
        visited_nodes=[
            "initialize",
            "mark_ready",
            "call_model",
        ],
    )


def test_scenario_observation_accepts_typed_execution_data() -> None:
    observation = create_observation()

    assert observation.scenario_id == ("v7.normal.test-observation")
    assert observation.run.run_id == "evaluation-run"
    assert len(observation.evidence_ledger) == 1
    assert len(observation.tool_calls) == 1
    assert observation.iteration_count == 1


def test_scenario_observation_round_trips_through_json() -> None:
    observation = create_observation()

    restored = EvaluationScenarioObservation.model_validate_json(observation.model_dump_json())

    assert restored == observation


def test_scenario_observation_rejects_mismatched_tool_run() -> None:
    with pytest.raises(
        ValidationError,
        match=("Observed tool-call run IDs must match the agent-run identity"),
    ):
        EvaluationScenarioObservation(
            scenario_id="v7.normal.mismatched-run",
            run=create_run_response(),
            tool_calls=[
                create_tool_call(
                    run_id="different-run",
                )
            ],
            iteration_count=1,
            max_iterations=6,
            visited_nodes=["initialize"],
        )


def test_scenario_observation_preserves_invalid_trajectory() -> None:
    observation = EvaluationScenarioObservation(
        scenario_id="v7.normal.invalid-trajectory",
        run=create_run_response(),
        iteration_count=7,
        max_iterations=6,
        visited_nodes=[],
    )

    assert observation.iteration_count == 7
    assert observation.max_iterations == 6
    assert observation.visited_nodes == []


def test_scenario_observation_rejects_unknown_fields() -> None:
    payload = {
        **create_observation().model_dump(mode="python"),
        "fabricated_score": 1.0,
    }

    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        EvaluationScenarioObservation.model_validate(payload)


def create_metric_results(
    *,
    failed_metric: EvaluationMetric | None = None,
) -> list[EvaluationMetricResult]:
    return [
        create_binary_metric_result(
            metric,
            metric != failed_metric,
            summary=f"Evaluated {metric.value}.",
            failure_details=[f"{metric.value} failed during evaluation."],
        )
        for metric in EvaluationMetric
    ]


def create_scenario_result(
    *,
    scenario_id: str = "v7.normal.test-result",
    status: EvaluationResultStatus = (EvaluationResultStatus.PASSED),
    failed_metric: EvaluationMetric | None = None,
) -> EvaluationScenarioResult:
    return EvaluationScenarioResult(
        scenario_id=scenario_id,
        scenario_version=1,
        fixture_id="test-result",
        status=status,
        metric_results=create_metric_results(failed_metric=failed_metric),
    )


def test_scenario_result_accepts_all_passing_metrics() -> None:
    result = create_scenario_result()

    assert result.status == EvaluationResultStatus.PASSED
    assert len(result.metric_results) == len(EvaluationMetric)
    assert all(metric_result.score == 1.0 for metric_result in result.metric_results)


def test_scenario_result_accepts_failed_metric() -> None:
    result = create_scenario_result(
        status=EvaluationResultStatus.FAILED,
        failed_metric=EvaluationMetric.CITATION_VALIDITY,
    )

    assert result.status == EvaluationResultStatus.FAILED
    assert [
        metric_result.metric
        for metric_result in result.metric_results
        if metric_result.score == 0.0
    ] == [EvaluationMetric.CITATION_VALIDITY]


def test_scenario_result_rejects_incomplete_metric_set() -> None:
    with pytest.raises(
        ValidationError,
        match="every evaluation metric exactly once",
    ):
        EvaluationScenarioResult(
            scenario_id="v7.normal.incomplete-result",
            scenario_version=1,
            fixture_id="incomplete-result",
            status=EvaluationResultStatus.PASSED,
            metric_results=create_metric_results()[:-1],
        )


def test_passed_scenario_rejects_failed_metric() -> None:
    with pytest.raises(
        ValidationError,
        match="must not contain failed metrics",
    ):
        create_scenario_result(
            status=EvaluationResultStatus.PASSED,
            failed_metric=EvaluationMetric.TOOL_SELECTION,
        )


def test_execution_error_requires_details_without_metrics() -> None:
    result = EvaluationScenarioResult(
        scenario_id="v7.normal.execution-error",
        scenario_version=1,
        fixture_id="execution-error",
        status=EvaluationResultStatus.ERROR,
        metric_results=[],
        error_type="RuntimeError",
        error_message="Synthetic evaluation failure.",
    )

    assert result.status == EvaluationResultStatus.ERROR
    assert result.metric_results == []
    assert result.error_type == "RuntimeError"


def test_execution_error_rejects_metric_results() -> None:
    with pytest.raises(
        ValidationError,
        match=("execution-error result must not contain metric results"),
    ):
        EvaluationScenarioResult(
            scenario_id="v7.normal.invalid-error",
            scenario_version=1,
            fixture_id="invalid-error",
            status=EvaluationResultStatus.ERROR,
            metric_results=create_metric_results(),
            error_type="RuntimeError",
            error_message="Synthetic evaluation failure.",
        )


def test_dataset_result_round_trips_passing_results() -> None:
    result = EvaluationDatasetResult(
        dataset_id="v7.core",
        dataset_version=1,
        status=EvaluationResultStatus.PASSED,
        scenario_results=[
            create_scenario_result(scenario_id="v7.normal.result-one"),
            create_scenario_result(scenario_id="v7.normal.result-two"),
        ],
    )

    restored = EvaluationDatasetResult.model_validate_json(result.model_dump_json())

    assert restored == result


def test_dataset_result_rejects_incorrect_status() -> None:
    with pytest.raises(
        ValidationError,
        match=("status must match its scenario result statuses"),
    ):
        EvaluationDatasetResult(
            dataset_id="v7.core",
            dataset_version=1,
            status=EvaluationResultStatus.FAILED,
            scenario_results=[create_scenario_result()],
        )


def test_dataset_result_rejects_duplicate_scenario_ids() -> None:
    duplicated_result = create_scenario_result()

    with pytest.raises(
        ValidationError,
        match="must have unique scenario IDs",
    ):
        EvaluationDatasetResult(
            dataset_id="v7.core",
            dataset_version=1,
            status=EvaluationResultStatus.PASSED,
            scenario_results=[
                duplicated_result,
                duplicated_result.model_copy(),
            ],
        )
