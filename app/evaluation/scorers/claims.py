from collections.abc import Sequence

from app.evaluation.contracts import (
    ClaimExpectation,
    ClaimLocation,
)
from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricResult,
    create_binary_metric_result,
)
from app.schemas.diagnosis import MaintenanceDiagnosis


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _diagnosis_text_at_location(
    diagnosis: MaintenanceDiagnosis,
    location: ClaimLocation,
) -> str:
    text_by_location = {
        ClaimLocation.SUMMARY: diagnosis.summary,
        ClaimLocation.CONFIDENCE_RATIONALE: (diagnosis.confidence_rationale),
        ClaimLocation.LIKELY_CAUSES: " ".join(diagnosis.likely_causes),
        ClaimLocation.RECOMMENDED_ACTIONS: " ".join(
            text
            for action in diagnosis.recommended_actions
            for text in (
                action.action,
                action.rationale,
            )
        ),
        ClaimLocation.SAFETY_NOTES: " ".join(diagnosis.safety_notes),
        ClaimLocation.ABSTENTION_REASON: (diagnosis.abstention_reason or ""),
    }

    return text_by_location[location]


def score_diagnosis_quality(
    required_claims: Sequence[ClaimExpectation],
    diagnosis: MaintenanceDiagnosis | None,
) -> EvaluationMetricResult:
    matched_claim_ids: list[str] = []
    missing_concepts_by_claim: dict[str, list[str]] = {}
    failure_details: list[str] = []

    for claim in required_claims:
        location_text = (
            _diagnosis_text_at_location(
                diagnosis,
                claim.location,
            )
            if diagnosis is not None
            else ""
        )
        normalized_location_text = _normalize_text(location_text)
        missing_concepts = [
            concept
            for concept in claim.required_concepts
            if _normalize_text(concept) not in normalized_location_text
        ]

        if missing_concepts:
            missing_concepts_by_claim[claim.claim_id] = missing_concepts
            failure_details.append(
                f"Claim '{claim.claim_id}' at "
                f"'{claim.location.value}' is missing required "
                f"concepts: {', '.join(missing_concepts)}."
            )
        else:
            matched_claim_ids.append(claim.claim_id)

    passed = not failure_details

    return create_binary_metric_result(
        EvaluationMetric.DIAGNOSIS_QUALITY,
        passed,
        summary=(
            "Diagnosis contained all required scenario concepts."
            if passed
            else "Diagnosis omitted required scenario concepts."
        ),
        expected={"required_claims": [claim.model_dump(mode="json") for claim in required_claims]},
        actual={
            "matched_claim_ids": matched_claim_ids,
            "missing_concepts_by_claim": (missing_concepts_by_claim),
        },
        failure_details=failure_details,
    )


def score_claim_support(
    required_claims: Sequence[ClaimExpectation],
    diagnosis: MaintenanceDiagnosis | None,
) -> EvaluationMetricResult:
    diagnosis_citations = {
        reference.citation for reference in (diagnosis.evidence if diagnosis is not None else [])
    }
    evaluated_claim_ids: list[str] = []
    supported_claim_ids: list[str] = []
    missing_citations_by_claim: dict[str, list[str]] = {}
    failure_details: list[str] = []

    for claim in required_claims:
        if not claim.citation_required:
            continue

        evaluated_claim_ids.append(claim.claim_id)
        missing_citations = sorted(set(claim.supporting_citations) - diagnosis_citations)

        if missing_citations:
            missing_citations_by_claim[claim.claim_id] = missing_citations
            failure_details.append(
                f"Claim '{claim.claim_id}' is missing supporting "
                f"citations: {', '.join(missing_citations)}."
            )
        else:
            supported_claim_ids.append(claim.claim_id)

    passed = not failure_details

    return create_binary_metric_result(
        EvaluationMetric.CLAIM_SUPPORT,
        passed,
        summary=(
            "All citation-required claims had their expected supporting citations."
            if passed
            else "Citation-required claims were missing expected supporting citations."
        ),
        expected={
            "citation_required_claims": [
                {
                    "claim_id": claim.claim_id,
                    "supporting_citations": (claim.supporting_citations),
                }
                for claim in required_claims
                if claim.citation_required
            ]
        },
        actual={
            "evaluated_claim_ids": evaluated_claim_ids,
            "supported_claim_ids": supported_claim_ids,
            "missing_citations_by_claim": (missing_citations_by_claim),
        },
        failure_details=failure_details,
    )


def _all_diagnosis_claim_text(
    diagnosis: MaintenanceDiagnosis,
) -> str:
    return " ".join(
        _diagnosis_text_at_location(
            diagnosis,
            location,
        )
        for location in ClaimLocation
    )


def score_forbidden_claims(
    forbidden_concepts: Sequence[str],
    diagnosis: MaintenanceDiagnosis | None,
) -> EvaluationMetricResult:
    diagnosis_text = (
        _normalize_text(_all_diagnosis_claim_text(diagnosis)) if diagnosis is not None else ""
    )
    matched_forbidden_concepts = [
        concept for concept in forbidden_concepts if _normalize_text(concept) in diagnosis_text
    ]
    passed = not matched_forbidden_concepts

    return create_binary_metric_result(
        EvaluationMetric.FORBIDDEN_CLAIMS,
        passed,
        summary=(
            "Diagnosis avoided all forbidden claim concepts."
            if passed
            else "Diagnosis contained forbidden claim concepts."
        ),
        expected={
            "forbidden_concepts_present": [],
        },
        actual={
            "forbidden_concepts_present": (matched_forbidden_concepts),
        },
        failure_details=[
            (f"Diagnosis contained forbidden concepts: {', '.join(matched_forbidden_concepts)}.")
        ],
    )
