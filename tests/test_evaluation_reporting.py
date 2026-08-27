from pathlib import Path

import pytest

from app.evaluation.execution import (
    EvaluationDatasetResult,
    EvaluationResultStatus,
    EvaluationScenarioResult,
)
from app.evaluation.reporting import write_evaluation_report


def create_error_result() -> EvaluationDatasetResult:
    return EvaluationDatasetResult(
        dataset_id="v7.core",
        dataset_version=1,
        status=EvaluationResultStatus.ERROR,
        scenario_results=[
            EvaluationScenarioResult(
                scenario_id="v7.normal.reporting-test",
                scenario_version=1,
                fixture_id="reporting-test",
                status=EvaluationResultStatus.ERROR,
                metric_results=[],
                error_type="RuntimeError",
                error_message="Synthetic reporting test error.",
            )
        ],
    )


def test_report_writer_creates_typed_json_and_parent_folders(
    tmp_path: Path,
) -> None:
    result = create_error_result()
    output_path = tmp_path / "reports" / "evaluation" / "result.json"

    written_path = write_evaluation_report(
        result,
        output_path,
    )
    restored = EvaluationDatasetResult.model_validate_json(output_path.read_text(encoding="utf-8"))

    assert written_path == output_path
    assert restored == result
    assert output_path.read_text(encoding="utf-8").endswith("\n")


def test_report_writer_refuses_implicit_overwrite(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "result.json"
    output_path.write_text(
        "existing report",
        encoding="utf-8",
    )

    with pytest.raises(
        FileExistsError,
        match="already exists",
    ):
        write_evaluation_report(
            create_error_result(),
            output_path,
        )

    assert output_path.read_text(encoding="utf-8") == "existing report"


def test_report_writer_allows_explicit_overwrite(
    tmp_path: Path,
) -> None:
    result = create_error_result()
    output_path = tmp_path / "result.json"
    output_path.write_text(
        "old report",
        encoding="utf-8",
    )

    write_evaluation_report(
        result,
        output_path,
        overwrite=True,
    )

    restored = EvaluationDatasetResult.model_validate_json(output_path.read_text(encoding="utf-8"))

    assert restored == result
    assert not (tmp_path / ".result.json.tmp").exists()
