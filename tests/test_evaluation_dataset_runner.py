from pathlib import Path

from app.evaluation.execution import (
    EvaluationResultStatus,
)
from app.evaluation.loader import load_evaluation_dataset
from app.evaluation.results import EvaluationMetricStatus
from app.evaluation.runner import run_evaluation_dataset

DATASET_PATH = Path("data/evaluation/v7_core.json")


def test_core_dataset_executes_all_scenarios(
    tmp_path: Path,
) -> None:
    dataset = load_evaluation_dataset(DATASET_PATH)

    result = run_evaluation_dataset(
        dataset,
        tmp_path / "v7-core",
    )

    failures = [
        {
            "fixture_id": scenario_result.fixture_id,
            "status": scenario_result.status.value,
            "error": (f"{scenario_result.error_type}: {scenario_result.error_message}"),
            "failed_metrics": [
                {
                    "metric": metric.metric.value,
                    "details": metric.details,
                }
                for metric in scenario_result.metric_results
                if metric.status == EvaluationMetricStatus.FAILED
            ],
        }
        for scenario_result in result.scenario_results
        if scenario_result.status != EvaluationResultStatus.PASSED
    ]

    assert result.status == EvaluationResultStatus.PASSED, failures
    assert len(result.scenario_results) == 15
    assert {scenario_result.fixture_id for scenario_result in result.scenario_results} == {
        scenario.fixture_id for scenario in dataset.scenarios
    }
    assert all(
        scenario_result.status == EvaluationResultStatus.PASSED
        for scenario_result in result.scenario_results
    )
