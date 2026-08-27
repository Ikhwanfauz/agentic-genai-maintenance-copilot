from pathlib import Path

import pytest

from app.evaluation import cli
from app.evaluation.execution import (
    EvaluationDatasetResult,
    EvaluationResultStatus,
    EvaluationScenarioResult,
)
from app.evaluation.results import (
    EvaluationMetric,
    create_binary_metric_result,
)

DATASET_PATH = Path("data/evaluation/v7_core.json")


def create_passed_result() -> EvaluationDatasetResult:
    metric_results = [
        create_binary_metric_result(
            metric,
            True,
            summary=f"{metric.value} passed.",
        )
        for metric in EvaluationMetric
    ]

    return EvaluationDatasetResult(
        dataset_id="v7.core",
        dataset_version=1,
        status=EvaluationResultStatus.PASSED,
        scenario_results=[
            EvaluationScenarioResult(
                scenario_id="v7.normal.cli-test",
                scenario_version=1,
                fixture_id="cli-test",
                status=EvaluationResultStatus.PASSED,
                metric_results=metric_results,
            )
        ],
    )


def test_cli_writes_passing_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = create_passed_result()
    output_path = tmp_path / "report.json"

    monkeypatch.setattr(
        cli,
        "run_evaluation_dataset",
        lambda dataset, working_directory: expected_result,
    )

    exit_code = cli.main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--output",
            str(output_path),
        ]
    )

    restored = EvaluationDatasetResult.model_validate_json(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert restored == expected_result


def test_cli_refuses_existing_report_without_running_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "report.json"
    output_path.write_text(
        "existing report",
        encoding="utf-8",
    )

    def fail_if_called(*_arguments, **_keywords):
        raise AssertionError("Dataset runner must not execute.")

    monkeypatch.setattr(
        cli,
        "run_evaluation_dataset",
        fail_if_called,
    )

    exit_code = cli.main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 2
    assert output_path.read_text(encoding="utf-8") == "existing report"


def test_cli_allows_explicit_report_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = create_passed_result()
    output_path = tmp_path / "report.json"
    output_path.write_text(
        "old report",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "run_evaluation_dataset",
        lambda dataset, working_directory: expected_result,
    )

    exit_code = cli.main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--output",
            str(output_path),
            "--overwrite",
        ]
    )

    restored = EvaluationDatasetResult.model_validate_json(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert restored == expected_result
