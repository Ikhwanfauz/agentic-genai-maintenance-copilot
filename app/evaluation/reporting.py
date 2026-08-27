from pathlib import Path

from app.evaluation.execution import EvaluationDatasetResult


def write_evaluation_report(
    result: EvaluationDatasetResult,
    output_path: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Persist one typed evaluation result as formatted JSON."""

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Evaluation report already exists: {output_path}")

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")

    try:
        temporary_path.write_text(
            f"{result.model_dump_json(indent=2)}\n",
            encoding="utf-8",
        )
        temporary_path.replace(output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return output_path
