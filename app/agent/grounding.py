import json
from collections.abc import Sequence

from langchain_core.messages import SystemMessage

from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.evidence import CollectedEvidence
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    EvidenceCoverage,
    EvidenceCoverageDecision,
    GroundingDecision,
)


def build_grounding_context_message(
    evidence_ledger: Sequence[CollectedEvidence],
    coverage: EvidenceCoverage | None,
    target_asset_code: str | None,
) -> SystemMessage:
    """Provide the synthesis model with an application-owned citation allowlist."""

    allowlist = [
        {
            "source_type": evidence.source_type.value,
            "source_id": evidence.source_id,
            "citation": evidence.citation,
            "asset_code": evidence.asset_code,
        }
        for evidence in evidence_ledger
        if evidence.asset_code == target_asset_code
    ]
    context = {
        "target_asset_code": target_asset_code,
        "coverage": coverage.model_dump(mode="json") if coverage else None,
        "citation_allowlist": allowlist,
    }

    return SystemMessage(
        content=(
            "Application-owned grounding metadata follows. For a diagnosis outcome, "
            "every evidence reference must exactly match one allowlist entry and the "
            "references must represent every required evidence source category.\n"
            f"{json.dumps(context, sort_keys=True)}"
        )
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


def _create_abstention(
    target_asset_code: str | None,
    violations: Sequence[str],
) -> MaintenanceDiagnosis:
    violation_text = "; ".join(violations)

    return MaintenanceDiagnosis(
        asset_code=target_asset_code,
        outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE,
        summary=(
            "A grounded maintenance diagnosis could not be completed because the "
            "structured output failed application evidence validation."
        ),
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale=(
            "The application could not verify the diagnosis against the eligible evidence ledger."
        ),
        likely_causes=[],
        evidence=[],
        recommended_actions=[],
        safety_notes=[
            "Do not act on an ungrounded diagnosis.",
            "Review the missing or unsupported evidence before continuing.",
        ],
        abstention_reason=f"Grounding validation failed: {violation_text}"[:1000],
    )


def enforce_grounded_diagnosis(
    diagnosis: MaintenanceDiagnosis,
    evidence_ledger: Sequence[CollectedEvidence],
    coverage: EvidenceCoverage | None,
    target_asset_code: str | None,
) -> tuple[MaintenanceDiagnosis, DiagnosisGroundingResult]:
    """Fail closed when a claimed diagnosis is not backed by eligible evidence."""

    if diagnosis.outcome == InvestigationOutcome.OUT_OF_SCOPE:
        return diagnosis, DiagnosisGroundingResult(
            decision=GroundingDecision.OUT_OF_SCOPE,
            original_outcome=diagnosis.outcome.value,
            final_outcome=diagnosis.outcome.value,
            matched_citations=[],
            violations=[],
            downgraded=False,
        )

    if diagnosis.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE:
        return diagnosis, DiagnosisGroundingResult(
            decision=GroundingDecision.ABSTAINED,
            original_outcome=diagnosis.outcome.value,
            final_outcome=diagnosis.outcome.value,
            matched_citations=[],
            violations=[],
            downgraded=False,
        )

    violations: list[str] = []

    if target_asset_code is None:
        violations.append("A target asset code is required for a diagnosis.")
    elif diagnosis.asset_code != target_asset_code:
        violations.append("The diagnosis asset does not match the investigation target.")

    if coverage is None:
        violations.append("Evidence coverage was not evaluated.")
    elif coverage.target_asset_code != target_asset_code:
        violations.append("Evidence coverage does not match the investigation target.")
    elif coverage.decision != EvidenceCoverageDecision.READY:
        violations.append("Required multi-source evidence coverage is incomplete.")

    eligible_evidence = [
        evidence for evidence in evidence_ledger if evidence.asset_code == target_asset_code
    ]
    evidence_by_key = {_evidence_key(evidence): evidence for evidence in eligible_evidence}
    reference_keys = [_reference_key(reference) for reference in diagnosis.evidence]

    if len(reference_keys) != len(set(reference_keys)):
        violations.append("Duplicate evidence references are not allowed.")

    matched_references = [
        reference
        for reference in diagnosis.evidence
        if _reference_key(reference) in evidence_by_key
    ]
    unmatched_count = len(diagnosis.evidence) - len(matched_references)

    if unmatched_count:
        violations.append(
            f"{unmatched_count} evidence reference(s) do not match the eligible ledger."
        )

    if coverage is not None:
        referenced_sources = {reference.source_type for reference in matched_references}
        missing_referenced_sources = [
            source for source in coverage.required_sources if source not in referenced_sources
        ]

        if missing_referenced_sources:
            missing_names = ", ".join(source.value for source in missing_referenced_sources)
            violations.append(
                f"Diagnosis references are missing required sources: {missing_names}."
            )

    matched_citations = [reference.citation for reference in matched_references]

    if violations:
        abstention = _create_abstention(target_asset_code, violations)
        return abstention, DiagnosisGroundingResult(
            decision=GroundingDecision.ABSTAINED,
            original_outcome=diagnosis.outcome.value,
            final_outcome=abstention.outcome.value,
            matched_citations=matched_citations,
            violations=violations,
            downgraded=True,
        )

    return diagnosis, DiagnosisGroundingResult(
        decision=GroundingDecision.GROUNDED,
        original_outcome=diagnosis.outcome.value,
        final_outcome=diagnosis.outcome.value,
        matched_citations=matched_citations,
        violations=[],
        downgraded=False,
    )
