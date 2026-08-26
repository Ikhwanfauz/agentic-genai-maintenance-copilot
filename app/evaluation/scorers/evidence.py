from collections import Counter
from collections.abc import Sequence

from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricResult,
    create_binary_metric_result,
)
from app.schemas.diagnosis import (
    EvidenceReference,
    EvidenceSourceType,
    MaintenanceDiagnosis,
)
from app.schemas.evidence import CollectedEvidence


def score_evidence_coverage(
    expected_sources: Sequence[EvidenceSourceType],
    evidence_ledger: Sequence[CollectedEvidence],
    target_asset_code: str | None,
) -> EvaluationMetricResult:
    expected_source_values = sorted({source.value for source in expected_sources})
    covered_source_values = sorted(
        {
            evidence.source_type.value
            for evidence in evidence_ledger
            if evidence.asset_code == target_asset_code
        }
    )
    missing_source_values = sorted(set(expected_source_values) - set(covered_source_values))
    passed = not missing_source_values

    return create_binary_metric_result(
        EvaluationMetric.EVIDENCE_COVERAGE,
        passed,
        summary=(
            "All required evidence sources were covered."
            if passed
            else "Required evidence coverage was incomplete."
        ),
        expected=expected_source_values,
        actual=covered_source_values,
        failure_details=[
            (f"Missing required evidence sources: {', '.join(missing_source_values)}.")
        ],
    )


def _reference_key(
    reference: EvidenceReference,
) -> tuple[str, str, str]:
    return (
        reference.source_type.value,
        reference.source_id,
        reference.citation,
    )


def _evidence_key(
    evidence: CollectedEvidence,
) -> tuple[str, str, str]:
    return (
        evidence.source_type.value,
        evidence.source_id,
        evidence.citation,
    )


def _display_reference_key(
    reference_key: tuple[str, str, str],
) -> str:
    return " | ".join(reference_key)


def score_citation_validity(
    diagnosis: MaintenanceDiagnosis | None,
    evidence_ledger: Sequence[CollectedEvidence],
    target_asset_code: str | None,
) -> EvaluationMetricResult:
    references = diagnosis.evidence if diagnosis is not None else []
    reference_keys = [_reference_key(reference) for reference in references]
    reference_counts = Counter(reference_keys)

    eligible_evidence_keys = {
        _evidence_key(evidence)
        for evidence in evidence_ledger
        if evidence.asset_code == target_asset_code
    }

    invalid_reference_keys = sorted(
        {
            reference_key
            for reference_key in reference_keys
            if reference_key not in eligible_evidence_keys
        }
    )
    duplicate_reference_keys = sorted(
        {reference_key for reference_key, count in reference_counts.items() if count > 1}
    )

    invalid_references = [
        _display_reference_key(reference_key) for reference_key in invalid_reference_keys
    ]
    duplicate_references = [
        _display_reference_key(reference_key) for reference_key in duplicate_reference_keys
    ]
    passed = not invalid_references and not duplicate_references

    failure_details: list[str] = []

    if invalid_references:
        failure_details.append(
            "Diagnosis contains references that do not match the eligible "
            f"evidence ledger: {', '.join(invalid_references)}."
        )

    if duplicate_references:
        failure_details.append(
            f"Diagnosis contains duplicate evidence references: {', '.join(duplicate_references)}."
        )

    expected_result = {
        "invalid_references": [],
        "duplicate_references": [],
    }
    actual_result = {
        "invalid_references": invalid_references,
        "duplicate_references": duplicate_references,
    }

    return create_binary_metric_result(
        EvaluationMetric.CITATION_VALIDITY,
        passed,
        summary=(
            "All diagnosis citations matched unique eligible evidence."
            if passed
            else "Diagnosis citation validation failed."
        ),
        expected=expected_result,
        actual=actual_result,
        failure_details=failure_details,
    )


def score_citation_completeness(
    expected_citations: Sequence[str],
    diagnosis: MaintenanceDiagnosis | None,
) -> EvaluationMetricResult:
    expected_citation_values = sorted(set(expected_citations))
    actual_citation_values = sorted(
        {reference.citation for reference in (diagnosis.evidence if diagnosis is not None else [])}
    )
    missing_citation_values = sorted(set(expected_citation_values) - set(actual_citation_values))
    passed = not missing_citation_values

    return create_binary_metric_result(
        EvaluationMetric.CITATION_COMPLETENESS,
        passed,
        summary=(
            "All required citations were included in the diagnosis."
            if passed
            else "The diagnosis omitted required citations."
        ),
        expected=expected_citation_values,
        actual=actual_citation_values,
        failure_details=[
            (f"Missing required diagnosis citations: {', '.join(missing_citation_values)}.")
        ],
    )
