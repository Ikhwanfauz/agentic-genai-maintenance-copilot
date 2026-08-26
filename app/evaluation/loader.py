import json
from pathlib import Path

from app.evaluation.contracts import EvaluationDataset


def load_evaluation_dataset(
    dataset_path: str | Path,
) -> EvaluationDataset:
    """Load and validate one versioned evaluation dataset."""

    normalized_path = str(dataset_path).strip()

    if not normalized_path:
        raise ValueError("Evaluation dataset path must not be empty.")

    resolved_path = Path(normalized_path)

    if not resolved_path.is_file():
        raise FileNotFoundError(f"Evaluation dataset was not found: {resolved_path}")

    payload = json.loads(resolved_path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise ValueError("Evaluation dataset root must be a JSON object.")

    return EvaluationDataset.model_validate(payload)
