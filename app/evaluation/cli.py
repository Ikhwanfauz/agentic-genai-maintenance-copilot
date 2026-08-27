import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from app.evaluation.execution import EvaluationResultStatus
from app.evaluation.loader import load_evaluation_dataset
from app.evaluation.reporting import write_evaluation_report
from app.evaluation.runner import run_evaluation_dataset

DEFAULT_DATASET_PATH = Path("data/evaluation/v7_core.json")
DEFAULT_OUTPUT_PATH = Path("reports/evaluation/v7_core_result.json")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run the deterministic Maintenance Copilot evaluation dataset.")
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to the versioned evaluation dataset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path for the machine-readable JSON report.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help=(
            "Optional fresh working directory for scenario "
            "databases, Chroma indexes, and checkpoints."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacement of an existing report.",
    )

    return parser


def _run_dataset(
    dataset_path: Path,
    work_directory: Path,
):
    dataset = load_evaluation_dataset(dataset_path)

    return run_evaluation_dataset(
        dataset,
        work_directory,
    )


def main(
    arguments: Sequence[str] | None = None,
) -> int:
    parser = build_argument_parser()
    parsed = parser.parse_args(arguments)

    try:
        if parsed.output.exists() and not parsed.overwrite:
            raise FileExistsError(f"Evaluation report already exists: {parsed.output}")

        if parsed.work_dir is None:
            with TemporaryDirectory(
                prefix="maintenance-copilot-evaluation-",
                ignore_cleanup_errors=True,
            ) as temporary_directory:
                result = _run_dataset(
                    parsed.dataset,
                    Path(temporary_directory),
                )
        else:
            result = _run_dataset(
                parsed.dataset,
                parsed.work_dir,
            )

        report_path = write_evaluation_report(
            result,
            parsed.output,
            overwrite=parsed.overwrite,
        )
    except Exception as error:
        print(
            f"Evaluation execution failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2

    passed_count = sum(
        scenario.status == EvaluationResultStatus.PASSED for scenario in result.scenario_results
    )
    failed_count = sum(
        scenario.status == EvaluationResultStatus.FAILED for scenario in result.scenario_results
    )
    error_count = sum(
        scenario.status == EvaluationResultStatus.ERROR for scenario in result.scenario_results
    )

    print(f"Dataset: {result.dataset_id}")
    print(f"Status: {result.status.value}")
    print(f"Scenarios: {passed_count} passed, {failed_count} failed, {error_count} errors")
    print(f"Report: {report_path}")

    if result.status == EvaluationResultStatus.PASSED:
        return 0

    if result.status == EvaluationResultStatus.FAILED:
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
