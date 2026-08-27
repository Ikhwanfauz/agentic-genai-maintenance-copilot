from pathlib import Path

import pytest

from app.evaluation.execution import (
    EvaluationResultStatus,
)
from app.evaluation.loader import load_evaluation_dataset
from app.evaluation.results import EvaluationMetricStatus
from app.evaluation.runner import run_evaluation_scenario

DATASET_PATH = Path("data/evaluation/v7_core.json")


def load_scenario(fixture_id: str):
    dataset = load_evaluation_dataset(DATASET_PATH)

    return next(scenario for scenario in dataset.scenarios if scenario.fixture_id == fixture_id)


@pytest.mark.parametrize(
    "fixture_id",
    [
        "p101-grounded-monitoring",
        "p101-sensor-data-unavailable",
        "p101-bypass-human-approval",
        "p101-direct-machinery-control",
    ],
)
def test_runner_executes_and_scores_real_graph_scenario(
    tmp_path: Path,
    fixture_id: str,
) -> None:
    scenario = load_scenario(fixture_id)

    result = run_evaluation_scenario(
        scenario,
        tmp_path / fixture_id,
    )

    failed_metrics = [
        (
            metric.metric.value,
            metric.summary,
            metric.details,
        )
        for metric in result.metric_results
        if metric.status == EvaluationMetricStatus.FAILED
    ]

    assert result.status == EvaluationResultStatus.PASSED, (
        f"error={result.error_type}: {result.error_message}; failed_metrics={failed_metrics}"
    )
    assert result.error_type is None
    assert result.error_message is None
    assert all(metric.status == EvaluationMetricStatus.PASSED for metric in result.metric_results)


def test_runner_returns_typed_error_for_reused_environment(
    tmp_path: Path,
) -> None:
    scenario = load_scenario("p101-grounded-monitoring")
    working_directory = tmp_path / "reused"

    first_result = run_evaluation_scenario(
        scenario,
        working_directory,
    )
    second_result = run_evaluation_scenario(
        scenario,
        working_directory,
    )

    assert first_result.status == EvaluationResultStatus.PASSED
    assert second_result.status == EvaluationResultStatus.ERROR
    assert second_result.metric_results == []
    assert second_result.error_type == "FileExistsError"
    assert "Evaluation database already exists" in (second_result.error_message)
